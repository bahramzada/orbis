from contextlib import asynccontextmanager, suppress
import asyncio
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
import json
import logging
import secrets
from time import monotonic, perf_counter
from typing import AsyncIterator, cast
from uuid import UUID, uuid4

from fastapi import Body, Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse
from httpx import HTTPError
from starlette import status

from app.agents import AgentOrchestrator, AgentRegistry, WORKERS
from app.config import Settings, get_settings
from app.db import DatabaseRepository, SCHEMA_INCOMPLETE_ERROR
from app.migration_runner import run_database_migrations
from app.metrics import metrics
from app.openrouter_client import OpenRouterClient
from app.security import (
    AuthContext,
    create_csrf_token,
    create_session_token,
    hash_csrf_token,
    hash_password,
    hash_session_token,
    password_needs_rehash,
    session_expires_at,
    verify_csrf_token,
    verify_password,
)
from app.schemas import (
    AdminUser,
    AgentGraphResponse,
    AgentProfile,
    AuthResponse,
    AuthUser,
    DelegationItem,
    EvaluationCompareRequest,
    EvaluationResult,
    HealthResponse,
    LoginRequest,
    MemoryCreateRequest,
    MemoryItem,
    PlanRequest,
    RegisterRequest,
    RerunSynthesisRequest,
    RerunWorkerRequest,
    RunDetail,
    RunRequest,
    SystemSettings,
    SystemSettingsUpdate,
    ToolCall,
    UserRole,
    UserRoleUpdateRequest,
    WorkerId,
    WorkflowTemplate,
    WorkflowLog,
    WorkflowRun,
    WorkflowRunSummary,
    WorkerResult,
)


registry = AgentRegistry()
logger = logging.getLogger(__name__)
AUTH_FAILURES_MAX_KEYS = 5_000
_auth_failures: OrderedDict[str, list[float]] = OrderedDict()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level.upper())
    settings.validate_security_settings()
    client = OpenRouterClient(settings)
    database = await _initialize_database(settings)
    app.state.system_settings = await database.get_system_settings()
    app.state.openrouter_client = client
    app.state.database = database
    app.state.orchestrator = AgentOrchestrator(client, registry, settings)
    app.state.agent_profiles = await _load_agent_profiles(database)
    app.state.memories = await database.list_memories()
    app.state.templates = await _load_templates(database)
    app.state.recent_runs = OrderedDict()
    app.state.evaluations = OrderedDict()
    yield
    await client.close()
    await database.close()


app = FastAPI(title="Orbis API", version="0.1.0", lifespan=lifespan)
settings = get_settings()

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=["GET", "POST", "PUT", "PATCH", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-CSRF-Token"],
)


@app.middleware("http")
async def record_request_metrics(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    started_at = perf_counter()
    status_code = "500"
    try:
        response = await call_next(request)
        _apply_security_headers(response)
        status_code = str(response.status_code)
        return response
    finally:
        elapsed = perf_counter() - started_at
        route = request.url.path
        labels = {
            "method": request.method,
            "path": route,
            "status": status_code,
        }
        metrics.increment("orbis_http_requests_total", labels)
        metrics.observe("orbis_http_request_duration_seconds", elapsed, labels)


@app.exception_handler(HTTPException)
async def http_exception_handler(_: Request, exc: HTTPException) -> JSONResponse:
    detail = "Request failed." if exc.status_code >= 500 else exc.detail
    response = JSONResponse(
        status_code=exc.status_code,
        content={"detail": detail},
        headers=exc.headers,
    )
    _apply_security_headers(response)
    return response


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception(
        "Unhandled request failed. path=%s error_class=%s",
        request.url.path,
        exc.__class__.__name__,
    )
    response = JSONResponse(
        status_code=500,
        content={"detail": "Internal server error."},
    )
    _apply_security_headers(response)
    return response


def get_orchestrator() -> AgentOrchestrator:
    return app.state.orchestrator


def get_client() -> OpenRouterClient:
    return app.state.openrouter_client


def get_database() -> DatabaseRepository:
    return app.state.database


async def _initialize_database(settings: Settings) -> DatabaseRepository:
    database = DatabaseRepository(settings)
    if not settings.is_database_configured:
        if settings.database_required:
            raise RuntimeError(
                "DATABASE_URL is required. Configure a PostgreSQL/Supabase URL "
                "before starting Orbis."
            )
        return database

    if settings.database_auto_migrate:
        await _run_database_migrations(settings, "startup")

    await database.init()
    if database.status == "ready":
        return database

    if database.error_code in {SCHEMA_INCOMPLETE_ERROR, "migration_conflict"}:
        logger.warning(
            "Database schema is not ready after first check; retrying migration. "
            "code=%s",
            database.error_code,
        )
        await _run_database_migrations(settings, "recovery")
        await database.close()
        database = DatabaseRepository(settings)
        await database.init()

    if settings.database_required and database.status != "ready":
        raise RuntimeError(
            "Database is required but unavailable. "
            f"code={database.error_code or 'unknown'}"
        )

    return database


async def _run_database_migrations(settings: Settings, phase: str) -> None:
    try:
        await run_database_migrations(settings)
    except Exception as exc:
        logger.warning(
            "Database migration failed. phase=%s error_class=%s",
            phase,
            exc.__class__.__name__,
        )
        logger.debug("Database migration traceback.", exc_info=True)


class StreamError:
    def __init__(self, detail: str) -> None:
        self.detail = detail


async def require_api_token(
    request: Request,
    authorization: str = Header(default=""),
    database: DatabaseRepository = Depends(get_database),
) -> AuthContext:
    expected = settings.orbis_api_token.strip()
    if (
        not expected
        and not settings.is_production
        and not database.is_persistence_configured
    ):
        return AuthContext(
            user_id="development",
            email="development@orbis.local",
            role="admin",
            source="development",
        )

    token = _bearer_token(authorization)
    if expected and token and secrets.compare_digest(token, expected):
        return AuthContext(
            user_id="api-token",
            email="api-token@orbis.local",
            role="admin",
            source="api-token",
        )

    session_token = request.cookies.get(settings.session_cookie_name, "")
    if session_token:
        session_token_hash = hash_session_token(session_token)
        record = await database.get_session_auth(session_token_hash)
        if record is not None:
            auth = AuthContext(
                user_id=record.user.id,
                email=record.user.email,
                role=record.user.role,
                source="session",
                session_token_hash=session_token_hash,
                csrf_hash=record.csrf_hash,
            )
            system_settings = await _current_system_settings(database)
            if not system_settings.system_enabled and not auth.is_admin:
                raise HTTPException(status_code=403, detail="System is disabled.")
            return auth

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Unauthorized.",
    )


def require_metrics_token(authorization: str = Header(default="")) -> None:
    expected = settings.effective_metrics_token
    if not expected and not settings.is_production:
        return
    if not expected or not _is_authorized(authorization, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized.",
        )


def _is_authorized(authorization: str, expected_token: str) -> bool:
    token = _bearer_token(authorization)
    if not token:
        return False
    return secrets.compare_digest(token, expected_token)


def _bearer_token(authorization: str) -> str:
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer":
        return ""
    return token.strip()


async def require_admin(
    auth: AuthContext = Depends(require_api_token),
) -> AuthContext:
    if not auth.is_admin:
        raise HTTPException(status_code=403, detail="Admin access is required.")
    return auth


async def require_state_changing_auth(
    request: Request,
    auth: AuthContext = Depends(require_api_token),
    x_csrf_token: str = Header(default="", alias="X-CSRF-Token"),
) -> AuthContext:
    if auth.source == "session" and not verify_csrf_token(x_csrf_token, auth.csrf_hash):
        raise HTTPException(status_code=403, detail="Invalid CSRF token.")
    return auth


async def require_admin_mutation(
    auth: AuthContext = Depends(require_state_changing_auth),
) -> AuthContext:
    if not auth.is_admin:
        raise HTTPException(status_code=403, detail="Admin access is required.")
    return auth


async def _current_system_settings(database: DatabaseRepository) -> SystemSettings:
    system_settings = await database.get_system_settings()
    app.state.system_settings = system_settings
    return system_settings


async def _issue_auth_response(
    user: AuthUser,
    system_settings: SystemSettings,
    database: DatabaseRepository,
    response: Response,
    request: Request,
) -> AuthResponse:
    token = create_session_token()
    csrf_token = create_csrf_token()
    await database.create_session(
        hash_session_token(token),
        user.id,
        session_expires_at(settings.auth_session_ttl_hours),
        hash_csrf_token(csrf_token),
        _request_user_agent(request),
        _request_ip(request),
    )
    _set_session_cookie(response, token)
    return AuthResponse(
        token=_legacy_empty_token(),
        csrf_token=csrf_token,
        user=user,
        system=system_settings,
    )


def _normalize_user_role(value: str) -> UserRole:
    if value in {"admin", "guest", "vip"}:
        return cast(UserRole, value)
    return "guest"


def _datetime_text(value: object) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _legacy_empty_token() -> str:
    return str()


def _apply_security_headers(response: Response) -> None:
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        max_age=settings.auth_session_ttl_hours * 60 * 60,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite=settings.normalized_session_cookie_samesite,
        domain=settings.session_cookie_domain.strip() or None,
        path="/",
    )


def _clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        key=settings.session_cookie_name,
        domain=settings.session_cookie_domain.strip() or None,
        path="/",
        samesite=settings.normalized_session_cookie_samesite,
        secure=settings.session_cookie_secure,
        httponly=True,
    )


def _request_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _request_user_agent(request: Request) -> str:
    return request.headers.get("user-agent", "")


def _auth_rate_limit_key(request: Request, email: str) -> str:
    return f"{_request_ip(request)}:{email.strip().lower()}"


def _ensure_auth_rate_limit(request: Request, email: str) -> None:
    key = _auth_rate_limit_key(request, email)
    now = monotonic()
    window_start = now - settings.auth_rate_limit_window_seconds
    failures = [value for value in _auth_failures.get(key, []) if value >= window_start]
    if failures:
        _auth_failures[key] = failures
        _auth_failures.move_to_end(key)
    elif key in _auth_failures:
        del _auth_failures[key]

    if len(failures) >= settings.auth_rate_limit_max_attempts:
        raise HTTPException(
            status_code=429,
            detail="Too many authentication attempts. Try again later.",
        )


def _record_auth_failure(request: Request, email: str) -> None:
    key = _auth_rate_limit_key(request, email)
    now = monotonic()
    window_start = now - settings.auth_rate_limit_window_seconds
    failures = [value for value in _auth_failures.get(key, []) if value >= window_start]
    failures.append(now)
    _auth_failures[key] = failures
    _auth_failures.move_to_end(key)
    while len(_auth_failures) > AUTH_FAILURES_MAX_KEYS:
        _auth_failures.popitem(last=False)


def _clear_auth_failures(request: Request, email: str) -> None:
    _auth_failures.pop(_auth_rate_limit_key(request, email), None)


def _ensure_admin_user_update_allowed(
    users: list[AdminUser],
    user_id: str,
    payload: UserRoleUpdateRequest,
    auth: AuthContext,
) -> None:
    target = next((user for user in users if user.id == user_id), None)
    if target is None:
        return
    if target.id == auth.user_id and payload.is_active is False:
        raise HTTPException(status_code=400, detail="Admins cannot disable themselves.")

    active_admin_count = sum(
        user.role == "admin" and user.is_active for user in users
    )
    target_will_remain_active = (
        target.is_active if payload.is_active is None else payload.is_active
    )
    target_will_remain_admin = payload.role == "admin" and target_will_remain_active
    target_is_active_admin = target.role == "admin" and target.is_active
    if target_is_active_admin and not target_will_remain_admin and active_admin_count <= 1:
        raise HTTPException(
            status_code=400,
            detail="At least one active admin must remain.",
        )


@app.get("/health", response_model=HealthResponse)
async def health(
    client: OpenRouterClient = Depends(get_client),
    database: DatabaseRepository = Depends(get_database),
) -> HealthResponse:
    return HealthResponse(
        status="ok",
        openrouter_configured=client.is_configured,
        database_configured=database.is_persistence_configured,
        database_status=database.status,
        database_error_code=database.error_code,
        model=client.model,
    )


@app.post("/api/auth/register", response_model=AuthResponse)
async def register_user(
    request: Request,
    response: Response,
    payload: RegisterRequest,
    database: DatabaseRepository = Depends(get_database),
) -> AuthResponse:
    if not database.is_configured:
        raise HTTPException(status_code=503, detail="Database is required for auth.")

    await database.delete_expired_sessions()
    system_settings = await _current_system_settings(database)
    if not system_settings.system_enabled:
        raise HTTPException(status_code=403, detail="System is disabled.")
    if not system_settings.register_enabled:
        raise HTTPException(status_code=403, detail="Registration is disabled.")

    email = str(payload.email).strip().lower()
    _ensure_auth_rate_limit(request, email)
    existing = await database.get_user_by_email(email)
    if existing is not None:
        _record_auth_failure(request, email)
        raise HTTPException(
            status_code=409,
            detail="Registration could not be completed.",
        )

    display_name = payload.display_name.strip() or email.split("@", 1)[0]
    user = await database.create_user(
        str(uuid4()),
        email,
        display_name,
        hash_password(payload.password),
    )
    if user is None:
        _record_auth_failure(request, email)
        raise HTTPException(status_code=500, detail="Registration could not be completed.")

    _clear_auth_failures(request, email)
    return await _issue_auth_response(user, system_settings, database, response, request)


@app.post("/api/auth/login", response_model=AuthResponse)
async def login_user(
    request: Request,
    response: Response,
    payload: LoginRequest,
    database: DatabaseRepository = Depends(get_database),
) -> AuthResponse:
    if not database.is_configured:
        raise HTTPException(status_code=503, detail="Database is required for auth.")

    await database.delete_expired_sessions()
    email = str(payload.email).strip().lower()
    _ensure_auth_rate_limit(request, email)
    row = await database.get_user_by_email(email)
    if row is None or not verify_password(payload.password, str(row["password_hash"])):
        _record_auth_failure(request, email)
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    if not bool(row["is_active"]):
        _record_auth_failure(request, email)
        raise HTTPException(status_code=403, detail="Invalid email or password.")

    user = AuthUser(
        id=str(row["id"]),
        email=str(row["email"]),
        display_name=str(row["display_name"]),
        role=_normalize_user_role(str(row["role"])),
        created_at=_datetime_text(row["created_at"]),
    )
    system_settings = await _current_system_settings(database)
    if not system_settings.system_enabled and user.role != "admin":
        raise HTTPException(status_code=403, detail="System is disabled.")

    if password_needs_rehash(str(row["password_hash"])):
        await database.update_password_hash(user.id, hash_password(payload.password))

    _clear_auth_failures(request, email)
    return await _issue_auth_response(user, system_settings, database, response, request)


@app.get("/api/auth/me", response_model=AuthResponse)
async def auth_me(
    auth: AuthContext = Depends(require_api_token),
    database: DatabaseRepository = Depends(get_database),
) -> AuthResponse:
    await database.delete_expired_sessions()
    system_settings = await _current_system_settings(database)
    if auth.source in {"api-token", "development"}:
        return AuthResponse(
            token=_legacy_empty_token(),
            csrf_token=_legacy_empty_token(),
            user=AuthUser(
                id=auth.user_id,
                email=auth.email,
                display_name="Orbis Admin",
                role="admin",
                created_at=datetime.now(UTC).isoformat(),
            ),
            system=system_settings,
        )

    user = await database.get_user_by_id(auth.user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="Unauthorized.")
    csrf_token = create_csrf_token()
    await database.rotate_session_csrf(auth.session_token_hash, hash_csrf_token(csrf_token))
    return AuthResponse(
        token=_legacy_empty_token(),
        csrf_token=csrf_token,
        user=user,
        system=system_settings,
    )


@app.post("/api/auth/logout")
async def logout_user(
    response: Response,
    auth: AuthContext = Depends(require_state_changing_auth),
    database: DatabaseRepository = Depends(get_database),
) -> dict[str, str]:
    if auth.session_token_hash:
        await database.delete_session(auth.session_token_hash)
    _clear_session_cookie(response)
    return {"status": "ok"}


@app.get("/api/admin/settings", response_model=SystemSettings)
async def get_admin_settings(
    _: AuthContext = Depends(require_admin),
    database: DatabaseRepository = Depends(get_database),
) -> SystemSettings:
    return await _current_system_settings(database)


@app.patch("/api/admin/settings", response_model=SystemSettings)
async def update_admin_settings(
    payload: SystemSettingsUpdate,
    _: AuthContext = Depends(require_admin_mutation),
    database: DatabaseRepository = Depends(get_database),
) -> SystemSettings:
    current = await _current_system_settings(database)
    updated = SystemSettings(
        system_enabled=(
            current.system_enabled
            if payload.system_enabled is None
            else payload.system_enabled
        ),
        register_enabled=(
            current.register_enabled
            if payload.register_enabled is None
            else payload.register_enabled
        ),
    )
    saved = await database.save_system_settings(updated)
    app.state.system_settings = saved
    return saved


@app.get("/api/admin/users", response_model=list[AdminUser])
async def list_admin_users(
    _: AuthContext = Depends(require_admin),
    database: DatabaseRepository = Depends(get_database),
) -> list[AdminUser]:
    return await database.list_users()


@app.patch("/api/admin/users/{user_id}", response_model=AdminUser)
async def update_admin_user(
    user_id: UUID,
    payload: UserRoleUpdateRequest,
    auth: AuthContext = Depends(require_admin_mutation),
    database: DatabaseRepository = Depends(get_database),
) -> AdminUser:
    user_id_text = str(user_id)
    users = await database.list_users()
    _ensure_admin_user_update_allowed(users, user_id_text, payload, auth)
    user = await database.update_user_role(user_id_text, payload.role, payload.is_active)
    if user is None:
        raise HTTPException(status_code=404, detail="User was not found.")
    return user


@app.get("/metrics")
async def get_metrics(_: None = Depends(require_metrics_token)) -> PlainTextResponse:
    if not settings.enable_metrics:
        raise HTTPException(status_code=404, detail="Metrics are disabled.")
    return PlainTextResponse(metrics.render_prometheus(), media_type="text/plain")


@app.get("/api/agents", response_model=AgentGraphResponse)
async def get_agents(_: AuthContext = Depends(require_api_token)) -> AgentGraphResponse:
    return registry.graph()


@app.post("/api/runs", response_model=WorkflowRun)
async def run_workflow(
    payload: RunRequest,
    _: AuthContext = Depends(require_state_changing_auth),
    orchestrator: AgentOrchestrator = Depends(get_orchestrator),
    client: OpenRouterClient = Depends(get_client),
    database: DatabaseRepository = Depends(get_database),
) -> WorkflowRun:
    if not client.is_configured:
        raise HTTPException(
            status_code=503,
            detail="OPENROUTER_API_KEY is not configured.",
        )

    try:
        memories = await _selected_memories(payload.memory_ids, database)
        profiles = _profiles_or_defaults(payload.agent_profiles)
        result = await orchestrator.run(
            payload.task,
            plan_override=payload.plan,
            agent_profiles=profiles,
            memory_items=memories,
            output_format=payload.output_format,
            enable_review_phase=payload.enable_review_phase,
        )
        await database.save_workflow_run(result)
        _remember_run(result)
        return result
    except HTTPError as exc:
        logger.exception("Workflow provider request failed.")
        raise HTTPException(
            status_code=502,
            detail="Workflow provider request failed.",
        ) from exc
    except (RuntimeError, ValueError, KeyError) as exc:
        logger.exception("Workflow execution failed.")
        raise HTTPException(status_code=500, detail="Workflow failed.") from exc


@app.get("/api/runs", response_model=list[WorkflowRunSummary])
async def list_workflow_runs(
    limit: int = Query(default=20, ge=1, le=100),
    _: None = Depends(require_api_token),
    database: DatabaseRepository = Depends(get_database),
) -> list[WorkflowRunSummary]:
    return await database.list_workflow_runs(limit)


@app.get("/api/runs/{run_id}", response_model=RunDetail)
async def get_run_detail(
    run_id: UUID,
    _: None = Depends(require_api_token),
    database: DatabaseRepository = Depends(get_database),
) -> RunDetail:
    run_id_text = str(run_id)
    detail = await database.get_workflow_run(run_id_text)
    if detail is not None:
        return _merge_cached_evaluations(detail)

    cached = app.state.recent_runs.get(run_id_text)
    if cached is not None:
        return _merge_cached_evaluations(cached)

    raise HTTPException(status_code=404, detail="Run was not found.")


@app.post("/api/plans", response_model=list[DelegationItem])
async def preview_plan(
    payload: PlanRequest,
    _: AuthContext = Depends(require_state_changing_auth),
    orchestrator: AgentOrchestrator = Depends(get_orchestrator),
    client: OpenRouterClient = Depends(get_client),
    database: DatabaseRepository = Depends(get_database),
) -> list[DelegationItem]:
    if not client.is_configured:
        raise HTTPException(
            status_code=503,
            detail="OPENROUTER_API_KEY is not configured.",
        )

    memories = await _selected_memories(payload.memory_ids, database)
    return await orchestrator.create_plan(
        payload.task,
        agent_profiles=_profiles_or_defaults(payload.agent_profiles),
        memory_items=memories,
    )


@app.get("/api/agent-profiles", response_model=list[AgentProfile])
async def list_agent_profiles(
    _: None = Depends(require_api_token),
    database: DatabaseRepository = Depends(get_database),
) -> list[AgentProfile]:
    profiles = await database.list_agent_profiles()
    if profiles:
        app.state.agent_profiles = profiles
        return profiles
    return app.state.agent_profiles


@app.put("/api/agent-profiles", response_model=list[AgentProfile])
async def save_agent_profiles(
    profiles: list[AgentProfile] = Body(max_length=4),
    _: AuthContext = Depends(require_state_changing_auth),
    database: DatabaseRepository = Depends(get_database),
) -> list[AgentProfile]:
    normalized = _profiles_or_defaults(profiles)
    app.state.agent_profiles = normalized
    await database.save_agent_profiles(normalized)
    return normalized


@app.get("/api/templates", response_model=list[WorkflowTemplate])
async def list_templates(
    _: AuthContext = Depends(require_api_token),
    database: DatabaseRepository = Depends(get_database),
) -> list[WorkflowTemplate]:
    templates = await database.list_templates()
    if templates:
        app.state.templates = templates
        return templates
    return app.state.templates


@app.get("/api/memories", response_model=list[MemoryItem])
async def list_memories(
    _: None = Depends(require_api_token),
    database: DatabaseRepository = Depends(get_database),
) -> list[MemoryItem]:
    memories = await database.list_memories()
    if database.is_configured:
        app.state.memories = memories
    return app.state.memories if not database.is_configured else memories


@app.post("/api/memories", response_model=MemoryItem)
async def create_memory(
    payload: MemoryCreateRequest,
    _: AuthContext = Depends(require_state_changing_auth),
    database: DatabaseRepository = Depends(get_database),
) -> MemoryItem:
    item = await database.create_memory(str(uuid4()), payload)
    app.state.memories = [item, *app.state.memories][: settings.max_recent_runs]
    return item


@app.post("/api/runs/{run_id}/rerun/worker/{worker_id}", response_model=RunDetail)
async def rerun_worker(
    run_id: UUID,
    worker_id: WorkerId,
    payload: RerunWorkerRequest,
    _: AuthContext = Depends(require_state_changing_auth),
    orchestrator: AgentOrchestrator = Depends(get_orchestrator),
    client: OpenRouterClient = Depends(get_client),
    database: DatabaseRepository = Depends(get_database),
) -> RunDetail:
    if not client.is_configured:
        raise HTTPException(
            status_code=503,
            detail="OPENROUTER_API_KEY is not configured.",
        )

    run_id_text = str(run_id)
    detail = await _get_existing_run(run_id_text, database)
    plan_item = next((item for item in detail.plan if item.worker_id == worker_id), None)
    if plan_item is None:
        raise HTTPException(status_code=404, detail="Worker was not found in this run.")

    item = DelegationItem(
        worker_id=worker_id,
        objective=payload.objective or plan_item.objective,
        expected_output=payload.expected_output or plan_item.expected_output,
        enabled=True,
    )
    result = await orchestrator.rerun_worker(
        detail.task,
        item,
        agent_profiles=_profiles_or_defaults(payload.agent_profiles),
        memory_items=await _selected_memories(payload.memory_ids, database),
    )
    detail.worker_results = _replace_worker_result(detail.worker_results, result)
    await database.update_run_outputs(
        run_id_text,
        detail.worker_results,
        detail.final_answer,
        detail.output_format,
    )
    _remember_run(detail)
    return detail


@app.post("/api/runs/{run_id}/rerun/synthesis", response_model=RunDetail)
async def rerun_synthesis(
    run_id: UUID,
    payload: RerunSynthesisRequest,
    _: AuthContext = Depends(require_state_changing_auth),
    orchestrator: AgentOrchestrator = Depends(get_orchestrator),
    client: OpenRouterClient = Depends(get_client),
    database: DatabaseRepository = Depends(get_database),
) -> RunDetail:
    if not client.is_configured:
        raise HTTPException(
            status_code=503,
            detail="OPENROUTER_API_KEY is not configured.",
        )

    run_id_text = str(run_id)
    detail = await _get_existing_run(run_id_text, database)
    detail.final_answer = await orchestrator.rerun_synthesis(
        detail.task,
        detail.worker_results,
        output_format=payload.output_format,
        memory_items=await _selected_memories(payload.memory_ids, database),
    )
    detail.output_format = payload.output_format
    await database.update_run_outputs(
        run_id_text,
        detail.worker_results,
        detail.final_answer,
        detail.output_format,
    )
    _remember_run(detail)
    return detail


@app.post("/api/evaluations/compare", response_model=list[EvaluationResult])
async def compare_evaluations(
    payload: EvaluationCompareRequest,
    _: AuthContext = Depends(require_state_changing_auth),
    database: DatabaseRepository = Depends(get_database),
) -> list[EvaluationResult]:
    results: list[EvaluationResult] = []
    for run_id in payload.run_ids:
        run_id_text = str(run_id)
        detail = await _get_existing_run(run_id_text, database)
        evaluation = _evaluate_run(detail, payload.rubric)
        await database.save_evaluation(evaluation)
        _remember_evaluation(run_id_text, evaluation)
        results.append(evaluation)
    return results


@app.post("/api/runs/stream")
async def stream_workflow(
    payload: RunRequest,
    _: AuthContext = Depends(require_state_changing_auth),
    orchestrator: AgentOrchestrator = Depends(get_orchestrator),
    client: OpenRouterClient = Depends(get_client),
    database: DatabaseRepository = Depends(get_database),
) -> StreamingResponse:
    if not client.is_configured:
        raise HTTPException(
            status_code=503,
            detail="OPENROUTER_API_KEY is not configured.",
        )

    async def event_stream() -> AsyncIterator[str]:
        queue: asyncio.Queue[WorkflowLog | ToolCall | WorkflowRun | StreamError | None] = (
            asyncio.Queue()
        )

        async def push_log(log: WorkflowLog) -> None:
            await queue.put(log)

        async def push_tool(tool_call: ToolCall) -> None:
            await queue.put(tool_call)

        async def execute() -> None:
            try:
                memories = await _selected_memories(payload.memory_ids, database)
                result = await orchestrator.run(
                    payload.task,
                    log_callback=push_log,
                    tool_callback=push_tool,
                    plan_override=payload.plan,
                    agent_profiles=_profiles_or_defaults(payload.agent_profiles),
                    memory_items=memories,
                    output_format=payload.output_format,
                    enable_review_phase=payload.enable_review_phase,
                )
                await database.save_workflow_run(result)
                _remember_run(result)
                await queue.put(result)
            except Exception:
                logger.exception("Workflow stream failed.")
                await queue.put(StreamError("Workflow failed."))
            finally:
                await queue.put(None)

        run_task = asyncio.create_task(execute())
        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                if isinstance(item, WorkflowLog):
                    yield _json_line("log", item.model_dump(mode="json"))
                elif isinstance(item, ToolCall):
                    yield _json_line("tool_call", item.model_dump(mode="json"))
                elif isinstance(item, WorkflowRun):
                    yield _json_line("result", item.model_dump(mode="json"))
                elif isinstance(item, StreamError):
                    yield _json_line("error", {"detail": item.detail})
        finally:
            if not run_task.done():
                run_task.cancel()
                with suppress(asyncio.CancelledError):
                    await run_task

    return StreamingResponse(event_stream(), media_type="application/x-ndjson")


def _json_line(event_type: str, payload: object) -> str:
    return json.dumps({"type": event_type, "payload": payload}) + "\n"


async def _load_agent_profiles(database: DatabaseRepository) -> list[AgentProfile]:
    profiles = await database.list_agent_profiles()
    return profiles or _default_agent_profiles()


async def _load_templates(database: DatabaseRepository) -> list[WorkflowTemplate]:
    templates = await database.list_templates()
    return templates or _default_templates()


def _default_agent_profiles() -> list[AgentProfile]:
    return [
        AgentProfile(
            id=cast(WorkerId, worker.id),
            name=worker.name,
            role=worker.role,
            goal=worker.goal,
            system_prompt="",
            model="",
            temperature=0.3 if worker.id != "reviewer" else 0.2,
            max_tokens=900,
            enabled=True,
        )
        for worker in WORKERS
    ]


def _default_templates() -> list[WorkflowTemplate]:
    return [
        WorkflowTemplate(
            id="market-research",
            name="Market research",
            description="Audience, positioning, risks, and launch recommendations.",
            task_prompt="Analyze the market opportunity, target audience, positioning, risks, and next steps for: ",
            output_format="markdown",
        ),
        WorkflowTemplate(
            id="code-architecture-review",
            name="Code architecture review",
            description="System design, bottlenecks, tradeoffs, and verification plan.",
            task_prompt="Review this software architecture and propose practical improvements: ",
            output_format="roadmap",
        ),
        WorkflowTemplate(
            id="startup-launch-plan",
            name="Startup launch plan",
            description="Go-to-market sequence, deliverables, messaging, and risk controls.",
            task_prompt="Create a startup launch plan for: ",
            output_format="roadmap",
        ),
        WorkflowTemplate(
            id="ui-audit",
            name="UI audit",
            description="UX issues, visual hierarchy, responsive risks, and fixes.",
            task_prompt="Audit this UI/UX and produce prioritized fixes: ",
            output_format="checklist",
        ),
        WorkflowTemplate(
            id="legal-safe-checklist",
            name="Legal-safe checklist",
            description="Non-legal risk checklist with verification notes.",
            task_prompt="Create a practical, non-legal-advice checklist for: ",
            output_format="checklist",
        ),
    ]


def _profiles_or_defaults(profiles: list[AgentProfile] | None) -> list[AgentProfile]:
    if not profiles:
        return app.state.agent_profiles
    default_by_id = {profile.id: profile for profile in _default_agent_profiles()}
    merged = {profile.id: profile for profile in app.state.agent_profiles}
    for profile in profiles:
        if profile.id in default_by_id:
            merged[profile.id] = profile
    return [merged[worker.id] for worker in WORKERS if worker.id in merged]


async def _selected_memories(
    memory_ids: list[UUID],
    database: DatabaseRepository,
) -> list[MemoryItem]:
    if not memory_ids:
        return []

    memories = await database.list_memories()
    if database.is_configured:
        app.state.memories = memories
    else:
        memories = app.state.memories

    selected = {str(memory_id) for memory_id in memory_ids}
    return [memory for memory in memories if memory.enabled and memory.id in selected]


def _remember_run(run: WorkflowRun | RunDetail) -> None:
    detail = RunDetail.model_validate(run.model_dump(mode="json"))
    detail.evaluations = app.state.evaluations.get(detail.run_id, detail.evaluations)
    app.state.recent_runs[detail.run_id] = detail
    app.state.recent_runs.move_to_end(detail.run_id)
    while len(app.state.recent_runs) > settings.max_recent_runs:
        app.state.recent_runs.popitem(last=False)


def _remember_evaluation(run_id: str, evaluation: EvaluationResult) -> None:
    evaluations = app.state.evaluations.setdefault(run_id, [])
    evaluations.insert(0, evaluation)
    del evaluations[settings.max_evaluations_per_run :]
    app.state.evaluations.move_to_end(run_id)
    while len(app.state.evaluations) > settings.max_recent_runs:
        app.state.evaluations.popitem(last=False)


async def _get_existing_run(
    run_id: str,
    database: DatabaseRepository,
) -> RunDetail:
    detail = await database.get_workflow_run(run_id)
    if detail is None:
        detail = app.state.recent_runs.get(run_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Run was not found.")
    return _merge_cached_evaluations(detail)


def _merge_cached_evaluations(detail: RunDetail) -> RunDetail:
    cached = app.state.evaluations.get(detail.run_id, [])
    cached_ids = {evaluation.id for evaluation in cached}
    detail.evaluations = [
        *cached,
        *[item for item in detail.evaluations if item.id not in cached_ids],
    ]
    return detail


def _replace_worker_result(
    results: list[WorkerResult],
    replacement: WorkerResult,
) -> list[WorkerResult]:
    replaced = False
    updated: list[WorkerResult] = []
    for result in results:
        if result.worker_id == replacement.worker_id and not replaced:
            updated.append(replacement)
            replaced = True
        else:
            updated.append(result)
    if not replaced:
        updated.append(replacement)
    return updated


def _evaluate_run(run: RunDetail, rubric: str) -> EvaluationResult:
    final_text = run.final_answer.strip()
    worker_count = len(run.worker_results)
    section_count = final_text.count("\n## ") + (1 if final_text.startswith("## ") else 0)
    completeness = min(100, 35 + worker_count * 10 + section_count * 8)
    actionability_terms = ("next", "step", "checklist", "plan", "addım", "icra", "test")
    actionability = min(
        100,
        45 + sum(term in final_text.lower() for term in actionability_terms) * 8,
    )
    uncertainty_terms = ("assumption", "verify", "risk", "fərziyyə", "yoxla", "risk")
    hallucination_risk = max(
        5,
        45 - sum(term in final_text.lower() for term in uncertainty_terms) * 7,
    )
    overall = round((completeness + actionability + (100 - hallucination_risk)) / 3)
    return EvaluationResult(
        id=str(uuid4()),
        run_id=run.run_id,
        rubric=rubric,
        completeness=completeness,
        actionability=actionability,
        hallucination_risk=hallucination_risk,
        overall=overall,
        notes="Heuristic score based on sections, worker coverage, action words, and risk language.",
        created_at=datetime.now(UTC).isoformat(),
    )
