import asyncio
from time import monotonic
from typing import cast
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request

from app.config import Settings
from app.db import DatabaseRepository, SessionAuthRecord, _sanitize_audit_detail
from app.main import (
    _auth_failures,
    _cleanup_expired_sessions,
    _current_system_settings,
    _is_authorized,
    app,
    get_database,
    require_api_token,
    settings,
)
from app.schemas import (
    AdminUser,
    AgentProfile,
    AuditEvent,
    AuthUser,
    MemoryCreateRequest,
    MemoryItem,
    RunDetail,
    SystemSettings,
    UserRole,
    WorkerResult,
    WorkflowTemplate,
    WorkflowRun,
    WorkflowRunSummary,
)
from app.security import hash_pbkdf2_password


AUTH_HEADERS = {"Authorization": "Bearer test-token"}


class FakeAuthDatabase:
    def __init__(self) -> None:
        self.system_settings = SystemSettings()
        self.users: dict[str, dict[str, object]] = {}
        self.sessions: dict[str, dict[str, str]] = {}
        self.memories: list[MemoryItem] = []
        self.agent_profiles: dict[str, list[AgentProfile]] = {}
        self.global_agent_profiles: list[AgentProfile] = []
        self.runs: dict[str, RunDetail] = {}
        self.audit_events: list[AuditEvent] = []
        self.rate_limit_counts: dict[str, int] = {}
        self.expired_session_delete_count = 0
        self.expired_rate_limit_delete_count = 0
        self.get_user_by_id_count = 0
        self.last_touch_interval: int | None = None
        self.session_auth_read_count = 0
        self.system_settings_read_count = 0
        self.csrf_rotation_count = 0

    @property
    def is_configured(self) -> bool:
        return True

    @property
    def is_persistence_configured(self) -> bool:
        return True

    @property
    def status(self) -> str:
        return "ready"

    @property
    def error_code(self) -> str:
        return ""

    async def get_system_settings(self) -> SystemSettings:
        self.system_settings_read_count += 1
        return self.system_settings

    async def save_system_settings(self, settings: SystemSettings) -> SystemSettings:
        self.system_settings = settings
        return settings

    async def create_user(
        self,
        user_id: str,
        email: str,
        display_name: str,
        password_hash: str,
    ) -> AuthUser:
        row = {
            "id": user_id,
            "email": email,
            "display_name": display_name,
            "password_hash": password_hash,
            "role": "guest",
            "is_active": True,
            "created_at": "2026-05-31T00:00:00+00:00",
            "updated_at": "2026-05-31T00:00:00+00:00",
        }
        self.users[user_id] = row
        return AuthUser(
            id=user_id,
            email=email,
            display_name=display_name,
            role="guest",
            created_at=str(row["created_at"]),
        )

    async def get_user_by_email(self, email: str) -> dict[str, object] | None:
        for row in self.users.values():
            if row["email"] == email:
                return row
        return None

    async def create_session(
        self,
        token_hash: str,
        user_id: str,
        expires_at: object,
        csrf_hash: str,
        user_agent: str = "",
        ip_address: str = "",
    ) -> None:
        self.sessions[token_hash] = {"user_id": user_id, "csrf_hash": csrf_hash}

    async def get_user_by_session(self, token_hash: str) -> AuthUser | None:
        session = self.sessions.get(token_hash)
        user_id = session["user_id"] if session else None
        if user_id is None:
            return None
        row = self.users[user_id]
        if not bool(row["is_active"]):
            return None
        return AuthUser(
            id=str(row["id"]),
            email=str(row["email"]),
            display_name=str(row["display_name"]),
            role=cast(UserRole, row["role"]),
            created_at=str(row["created_at"]),
        )

    async def get_session_auth(
        self,
        token_hash: str,
        touch_interval_seconds: int = 300,
    ) -> SessionAuthRecord | None:
        self.session_auth_read_count += 1
        self.last_touch_interval = touch_interval_seconds
        user = await self.get_user_by_session(token_hash)
        session = self.sessions.get(token_hash)
        if user is None or session is None:
            return None
        return SessionAuthRecord(user=user, csrf_hash=session["csrf_hash"])

    async def rotate_session_csrf(self, token_hash: str, csrf_hash: str) -> None:
        self.csrf_rotation_count += 1
        if token_hash in self.sessions:
            self.sessions[token_hash]["csrf_hash"] = csrf_hash

    async def delete_expired_sessions(self) -> None:
        self.expired_session_delete_count += 1
        return None

    async def update_password_hash(self, user_id: str, password_hash: str) -> None:
        self.users[user_id]["password_hash"] = password_hash

    async def get_user_by_id(self, user_id: str) -> AuthUser | None:
        self.get_user_by_id_count += 1
        row = self.users.get(user_id)
        if row is None:
            return None
        return AuthUser(
            id=str(row["id"]),
            email=str(row["email"]),
            display_name=str(row["display_name"]),
            role=cast(UserRole, row["role"]),
            created_at=str(row["created_at"]),
        )

    async def delete_session(self, token_hash: str) -> None:
        self.sessions.pop(token_hash, None)

    async def list_users(self) -> list[AdminUser]:
        return [
            AdminUser(
                id=str(row["id"]),
                email=str(row["email"]),
                display_name=str(row["display_name"]),
                role=cast(UserRole, row["role"]),
                created_at=str(row["created_at"]),
                is_active=bool(row["is_active"]),
                updated_at=str(row["updated_at"]),
            )
            for row in self.users.values()
        ]

    async def update_user_role(
        self,
        user_id: str,
        role: UserRole,
        is_active: bool | None,
    ) -> AdminUser | None:
        row = self.users.get(user_id)
        if row is None:
            return None
        row["role"] = role
        if is_active is not None:
            row["is_active"] = is_active
        row["updated_at"] = "2026-05-31T00:01:00+00:00"
        return AdminUser(
            id=str(row["id"]),
            email=str(row["email"]),
            display_name=str(row["display_name"]),
            role=cast(UserRole, row["role"]),
            created_at=str(row["created_at"]),
            is_active=bool(row["is_active"]),
            updated_at=str(row["updated_at"]),
        )

    async def create_memory(
        self,
        item_id: str,
        payload: MemoryCreateRequest,
        owner_user_id: str,
    ) -> MemoryItem:
        item = MemoryItem(
            id=item_id,
            owner_user_id=owner_user_id,
            title=payload.title,
            category=payload.category,
            content=payload.content,
            enabled=payload.enabled,
            created_at="2026-05-31T00:00:00+00:00",
        )
        self.memories.append(item)
        return item

    async def list_memories(
        self,
        *,
        owner_user_id: str | None = None,
        include_all: bool = False,
    ) -> list[MemoryItem]:
        if include_all:
            return list(self.memories)
        return [
            memory
            for memory in self.memories
            if owner_user_id is not None and memory.owner_user_id == owner_user_id
        ]

    async def list_templates(self) -> list[WorkflowTemplate]:
        return []

    async def list_global_agent_profiles(self) -> list[AgentProfile]:
        return list(self.global_agent_profiles)

    async def list_agent_profiles(
        self,
        owner_user_id: str | None = None,
    ) -> list[AgentProfile]:
        if owner_user_id is None:
            return await self.list_global_agent_profiles()
        return list(self.agent_profiles.get(owner_user_id, []))

    async def save_agent_profiles(
        self,
        profiles: list[AgentProfile],
        owner_user_id: str | None = None,
    ) -> None:
        if owner_user_id is None:
            self.global_agent_profiles = list(profiles)
            return
        self.agent_profiles[owner_user_id] = list(profiles)

    async def save_workflow_run(
        self,
        run: WorkflowRun,
        owner_user_id: str,
    ) -> None:
        run.owner_user_id = owner_user_id
        self.runs[run.run_id] = RunDetail.model_validate(run.model_dump(mode="json"))

    async def list_workflow_runs(
        self,
        limit: int = 20,
        *,
        owner_user_id: str | None = None,
        include_all: bool = False,
    ) -> list[WorkflowRunSummary]:
        runs = list(self.runs.values())
        if not include_all:
            runs = [
                run
                for run in runs
                if owner_user_id is not None and run.owner_user_id == owner_user_id
            ]
        return [
            WorkflowRunSummary(
                run_id=run.run_id,
                task=run.task,
                model=run.model,
                status=run.status,
                created_at="2026-05-31T00:00:00+00:00",
                completed_at="2026-05-31T00:00:01+00:00",
                owner_user_id=run.owner_user_id,
            )
            for run in runs[:limit]
        ]

    async def get_workflow_run(
        self,
        run_id: str,
        *,
        owner_user_id: str | None = None,
        include_all: bool = False,
    ) -> RunDetail | None:
        run = self.runs.get(run_id)
        if run is None:
            return None
        if include_all:
            return run
        if owner_user_id is not None and run.owner_user_id == owner_user_id:
            return run
        return None

    async def update_run_outputs(
        self,
        run_id: str,
        worker_results: list[WorkerResult],
        final_answer: str,
        output_format: str,
        *,
        owner_user_id: str | None = None,
        include_all: bool = False,
    ) -> None:
        run = await self.get_workflow_run(
            run_id,
            owner_user_id=owner_user_id,
            include_all=include_all,
        )
        if run is None:
            return
        run.worker_results = worker_results
        run.final_answer = final_answer
        run.output_format = output_format

    async def save_evaluation(self, _: object) -> None:
        return None

    async def record_audit_event(
        self,
        *,
        event_id: str,
        action: str,
        actor_user_id: str | None = None,
        actor_email: str = "",
        actor_role: str = "",
        resource_type: str = "",
        resource_id: str = "",
        ip_address: str = "",
        user_agent: str = "",
        detail: dict[str, object] | None = None,
    ) -> None:
        self.audit_events.insert(
            0,
            AuditEvent(
                id=event_id,
                actor_user_id=actor_user_id,
                actor_email=actor_email,
                actor_role=actor_role,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                ip_address=ip_address,
                user_agent=user_agent,
                detail=detail or {},
                created_at="2026-05-31T00:00:00+00:00",
            ),
        )

    async def list_audit_events(self, limit: int = 100) -> list[AuditEvent]:
        return self.audit_events[:limit]

    async def increment_rate_limit(self, key: str, *, window_seconds: int) -> int:
        _ = window_seconds
        self.rate_limit_counts[key] = self.rate_limit_counts.get(key, 0) + 1
        return self.rate_limit_counts[key]

    async def reset_rate_limit(self, key: str) -> None:
        self.rate_limit_counts.pop(key, None)

    async def delete_expired_rate_limits(self) -> None:
        self.expired_rate_limit_delete_count += 1


@pytest.fixture(autouse=True)
def secure_test_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "app_env", "development")
    monkeypatch.setattr(settings, "orbis_api_token", "test-token")
    monkeypatch.setattr(settings, "metrics_api_token", "")
    monkeypatch.setattr(settings, "database_url", "")
    monkeypatch.setattr(settings, "database_required", False)
    monkeypatch.setattr(settings, "database_auto_create_tables", False)
    monkeypatch.setattr(settings, "database_auto_migrate", False)
    monkeypatch.setattr(settings, "database_ssl", "require")
    monkeypatch.setattr(settings, "session_cookie_name", "orbis_session")
    monkeypatch.setattr(settings, "session_cookie_secure", False)
    monkeypatch.setattr(settings, "session_cookie_samesite", "lax")
    monkeypatch.setattr(settings, "session_cookie_domain", "")
    monkeypatch.setattr(settings, "auth_session_cleanup_interval_seconds", 900)
    monkeypatch.setattr(settings, "auth_session_touch_interval_seconds", 300)
    monkeypatch.setattr(settings, "auth_rate_limit_max_attempts", 5)
    monkeypatch.setattr(settings, "auth_rate_limit_window_seconds", 900)
    monkeypatch.setattr(settings, "auth_rate_limit_backend", "postgres")
    monkeypatch.setattr(settings, "workflow_rate_limit_per_hour", 20)
    monkeypatch.setattr(settings, "workflow_rate_limit_per_day", 100)
    monkeypatch.setattr(settings, "workflow_max_concurrent_per_user", 1)
    monkeypatch.setattr(settings, "rate_limit_cleanup_interval_seconds", 3600)
    monkeypatch.setattr(settings, "system_settings_cache_ttl_seconds", 30)
    _auth_failures.clear()


def _register_session(
    client: TestClient,
    fake_database: FakeAuthDatabase,
    *,
    email: str = "person@example.com",
    role: UserRole = "guest",
) -> tuple[str, str]:
    response = client.post(
        "/api/auth/register",
        json={
            "email": email,
            "password": "strong-password",  # pragma: allowlist secret
            "display_name": email.split("@", 1)[0],
        },
    )
    assert response.status_code == 200
    payload = response.json()
    user_id = str(payload["user"]["id"])
    fake_database.users[user_id]["role"] = role
    return user_id, str(payload["csrf_token"])


def _sample_run(owner_user_id: str | None) -> RunDetail:
    run_id = str(uuid4())
    return RunDetail(
        run_id=run_id,
        owner_user_id=owner_user_id,
        task="Create a launch plan.",
        model="test-model",
        status="completed",
        logs=[],
        plan=[],
        worker_results=[],
        final_answer="Done.",
        tool_calls=[],
        output_format="markdown",
        duration_ms=10,
        estimated_tokens=20,
        estimated_cost_usd=0.0,
        evaluations=[],
    )


def test_bearer_token_auth_uses_constant_time_compare() -> None:
    assert _is_authorized("Bearer test-token", "test-token") is True
    assert _is_authorized("Bearer wrong-token", "test-token") is False
    assert _is_authorized("Basic test-token", "test-token") is False


def test_audit_detail_redacts_sensitive_values() -> None:
    sanitized = _sanitize_audit_detail(
        {
            "password": "strong-password",
            "Authorization": "Bearer test-token",
            "database_url": "postgresql://user:secret@example.com/db",
            "nested": {"csrf_token": "csrf", "normal": "kept"},
        }
    )

    assert sanitized == {
        "password": "[redacted]",
        "Authorization": "[redacted]",
        "database_url": "[redacted]",
        "nested": {"csrf_token": "[redacted]", "normal": "kept"},
    }


def test_mutating_endpoints_require_authorization() -> None:
    fake_database = FakeAuthDatabase()
    app.dependency_overrides[get_database] = lambda: fake_database
    try:
        with TestClient(app) as client:
            unauthorized = client.post(
                "/api/memories",
                json={
                    "title": "Brand voice",
                    "category": "brand",
                    "content": "Use concise language.",
                    "enabled": True,
                },
            )
            bearer = client.post(
                "/api/memories",
                headers=AUTH_HEADERS,
                json={
                    "title": "Brand voice",
                    "category": "brand",
                    "content": "Use concise language.",
                    "enabled": True,
                },
            )
            _, csrf_token = _register_session(client, fake_database)
            authorized = client.post(
                "/api/memories",
                headers={"X-CSRF-Token": csrf_token},
                json={
                    "title": "Brand voice",
                    "category": "brand",
                    "content": "Use concise language.",
                    "enabled": True,
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert unauthorized.status_code == 401
    assert bearer.status_code == 401
    assert authorized.status_code == 200


def test_metrics_requires_authorization_when_token_is_configured() -> None:
    with TestClient(app) as client:
        unauthorized = client.get("/metrics")
        authorized = client.get("/metrics", headers=AUTH_HEADERS)

    assert unauthorized.status_code == 401
    assert authorized.status_code == 200


def test_system_read_endpoints_require_authorization() -> None:
    fake_database = FakeAuthDatabase()
    app.dependency_overrides[get_database] = lambda: fake_database
    try:
        with TestClient(app) as client:
            agents_unauthorized = client.get("/api/agents")
            templates_unauthorized = client.get("/api/templates")
            agents_bearer = client.get("/api/agents", headers=AUTH_HEADERS)
            templates_bearer = client.get("/api/templates", headers=AUTH_HEADERS)
            _register_session(client, fake_database)
            agents_authorized = client.get("/api/agents")
            templates_authorized = client.get("/api/templates")
    finally:
        app.dependency_overrides.clear()

    assert agents_unauthorized.status_code == 401
    assert templates_unauthorized.status_code == 401
    assert agents_bearer.status_code == 401
    assert templates_bearer.status_code == 401
    assert agents_authorized.status_code == 200
    assert templates_authorized.status_code == 200


def test_cors_preflight_allows_admin_patch_requests() -> None:
    with TestClient(app) as client:
        response = client.options(
            "/api/admin/settings",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "PATCH",
                "Access-Control-Request-Headers": "X-CSRF-Token",
            },
        )

    assert response.status_code == 200
    assert "PATCH" in response.headers["access-control-allow-methods"]
    assert "X-CSRF-Token" in response.headers["access-control-allow-headers"]


def test_development_fallback_does_not_bypass_configured_database_auth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "orbis_api_token", "")
    fake_database = FakeAuthDatabase()
    request = Request(
        {
            "type": "http",
            "headers": [],
            "client": ("testclient", 50000),
            "path": "/",
        }
    )

    with pytest.raises(HTTPException) as caught:
        asyncio.run(
            require_api_token(request, "", cast(DatabaseRepository, fake_database))
        )

    assert caught.value.status_code == 401


def test_register_creates_guest_user_and_session() -> None:
    fake_database = FakeAuthDatabase()
    app.dependency_overrides[get_database] = lambda: fake_database
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/auth/register",
                json={
                    "email": "person@example.com",
                    "password": "strong-password",  # pragma: allowlist secret
                    "display_name": "Person",
                },
            )
    finally:
        app.dependency_overrides.clear()

    payload = response.json()
    assert response.status_code == 200
    assert payload["user"]["role"] == "guest"
    assert payload["token"] == ""
    assert payload["csrf_token"]
    assert "orbis_session=" in response.headers["set-cookie"]
    assert "HttpOnly" in response.headers["set-cookie"]
    assert len(fake_database.users) == 1
    assert len(fake_database.sessions) == 1


def test_expired_session_cleanup_is_throttled() -> None:
    fake_database = FakeAuthDatabase()
    app.state.last_session_cleanup_at = 0.0
    app.state.last_session_cleanup_database_id = None

    asyncio.run(_cleanup_expired_sessions(cast(DatabaseRepository, fake_database)))
    asyncio.run(_cleanup_expired_sessions(cast(DatabaseRepository, fake_database)))

    assert fake_database.expired_session_delete_count == 1


def test_system_settings_cache_reuses_recent_value() -> None:
    fake_database = FakeAuthDatabase()
    app.state.system_settings = fake_database.system_settings
    app.state.system_settings_cached_at = monotonic()
    app.state.system_settings_cache_database_id = id(fake_database)

    cached = asyncio.run(_current_system_settings(cast(DatabaseRepository, fake_database)))
    refreshed = asyncio.run(
        _current_system_settings(cast(DatabaseRepository, fake_database), force_refresh=True)
    )

    assert cached == fake_database.system_settings
    assert refreshed == fake_database.system_settings
    assert fake_database.system_settings_read_count == 1


def test_secure_cookie_flags_can_be_enforced(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "session_cookie_secure", True)
    fake_database = FakeAuthDatabase()
    app.dependency_overrides[get_database] = lambda: fake_database
    try:
        with TestClient(app, base_url="https://testserver") as client:
            response = client.post(
                "/api/auth/register",
                json={
                    "email": "secure@example.com",
                    "password": "strong-password",  # pragma: allowlist secret
                    "display_name": "Secure",
                },
            )
    finally:
        app.dependency_overrides.clear()

    cookie = response.headers["set-cookie"]
    assert response.status_code == 200
    assert "Secure" in cookie
    assert "SameSite=lax" in cookie


def test_cookie_session_requires_csrf_for_mutations() -> None:
    fake_database = FakeAuthDatabase()
    app.dependency_overrides[get_database] = lambda: fake_database
    try:
        with TestClient(app) as client:
            register = client.post(
                "/api/auth/register",
                json={
                    "email": "csrf@example.com",
                    "password": "strong-password",  # pragma: allowlist secret
                    "display_name": "CSRF",
                },
            )
            missing_csrf = client.post("/api/auth/logout")
            valid_csrf = client.post(
                "/api/auth/logout",
                headers={"X-CSRF-Token": register.json()["csrf_token"]},
            )
    finally:
        app.dependency_overrides.clear()

    assert register.status_code == 200
    assert missing_csrf.status_code == 403
    assert valid_csrf.status_code == 200


def test_auth_me_uses_session_context_and_touch_interval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "auth_session_touch_interval_seconds", 123)
    fake_database = FakeAuthDatabase()
    app.dependency_overrides[get_database] = lambda: fake_database
    try:
        with TestClient(app) as client:
            register = client.post(
                "/api/auth/register",
                json={
                    "email": "me@example.com",
                    "password": "strong-password",  # pragma: allowlist secret
                    "display_name": "Me",
                },
            )
            response = client.get("/api/auth/me")
    finally:
        app.dependency_overrides.clear()

    assert register.status_code == 200
    assert response.status_code == 200
    assert response.json()["user"]["email"] == "me@example.com"
    assert fake_database.last_touch_interval == 123
    assert fake_database.get_user_by_id_count == 0
    assert fake_database.csrf_rotation_count == 1


def test_register_respects_registration_switch() -> None:
    fake_database = FakeAuthDatabase()
    fake_database.system_settings = SystemSettings(register_enabled=False)
    app.dependency_overrides[get_database] = lambda: fake_database
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/auth/register",
                json={
                    "email": "person@example.com",
                    "password": "strong-password",  # pragma: allowlist secret
                    "display_name": "Person",
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
    assert response.json()["detail"] == "Registration is disabled."


def test_login_rate_limit_blocks_repeated_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "auth_rate_limit_max_attempts", 2)
    fake_database = FakeAuthDatabase()
    app.dependency_overrides[get_database] = lambda: fake_database
    try:
        with TestClient(app) as client:
            payload = {
                "email": "missing@example.com",
                "password": "bad",  # pragma: allowlist secret
            }
            first = client.post(
                "/api/auth/login",
                json=payload,
            )
            second = client.post(
                "/api/auth/login",
                json=payload,
            )
            locked = client.post(
                "/api/auth/login",
                json=payload,
            )
    finally:
        app.dependency_overrides.clear()

    assert first.status_code == 401
    assert second.status_code == 401
    assert locked.status_code == 429


def test_pbkdf2_password_is_rehashed_to_argon2_on_login() -> None:
    fake_database = FakeAuthDatabase()
    user_id = str(uuid4())
    fake_database.users[user_id] = {
        "id": user_id,
        "email": "legacy@example.com",
        "display_name": "Legacy",
        "password_hash": hash_pbkdf2_password("strong-password"),  # pragma: allowlist secret
        "role": "guest",
        "is_active": True,
        "created_at": "2026-05-31T00:00:00+00:00",
        "updated_at": "2026-05-31T00:00:00+00:00",
    }
    app.dependency_overrides[get_database] = lambda: fake_database
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/auth/login",
                json={
                    "email": "legacy@example.com",
                    "password": "strong-password",  # pragma: allowlist secret
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert str(fake_database.users[user_id]["password_hash"]).startswith("$argon2")


def test_admin_can_update_system_settings_and_user_role() -> None:
    fake_database = FakeAuthDatabase()
    created = asyncio.run(
        fake_database.create_user(
            str(uuid4()),
            "person@example.com",
            "Person",
            "stored-password-hash",
        )
    )
    app.dependency_overrides[get_database] = lambda: fake_database
    try:
        with TestClient(app) as client:
            _, csrf_token = _register_session(
                client,
                fake_database,
                email="admin@example.com",
                role="admin",
            )
            settings_response = client.patch(
                "/api/admin/settings",
                headers={"X-CSRF-Token": csrf_token},
                json={"system_enabled": False, "register_enabled": False},
            )
            role_response = client.patch(
                f"/api/admin/users/{created.id}",
                headers={"X-CSRF-Token": csrf_token},
                json={"role": "vip", "is_active": False},
            )
    finally:
        app.dependency_overrides.clear()

    assert settings_response.status_code == 200
    assert settings_response.json() == {
        "system_enabled": False,
        "register_enabled": False,
    }
    assert role_response.status_code == 200
    assert role_response.json()["role"] == "vip"
    assert role_response.json()["is_active"] is False


def test_last_active_admin_cannot_be_downgraded() -> None:
    fake_database = FakeAuthDatabase()
    app.dependency_overrides[get_database] = lambda: fake_database
    try:
        with TestClient(app) as client:
            admin_id, csrf_token = _register_session(
                client,
                fake_database,
                email="admin@example.com",
                role="admin",
            )
            response = client.patch(
                f"/api/admin/users/{admin_id}",
                headers={"X-CSRF-Token": csrf_token},
                json={"role": "vip", "is_active": True},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert response.json()["detail"] == "At least one active admin must remain."


def test_public_health_is_minimal() -> None:
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_admin_health_reports_database_status() -> None:
    fake_database = FakeAuthDatabase()
    app.dependency_overrides[get_database] = lambda: fake_database
    try:
        with TestClient(app) as client:
            _register_session(
                client,
                fake_database,
                email="admin@example.com",
                role="admin",
            )
            response = client.get("/api/admin/health")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["database_status"] == "ready"
    assert response.json()["database_error_code"] == ""


def test_bearer_token_is_service_scoped_not_admin_or_user_auth() -> None:
    fake_database = FakeAuthDatabase()
    app.dependency_overrides[get_database] = lambda: fake_database
    try:
        with TestClient(app) as client:
            user_endpoint = client.get("/api/agents", headers=AUTH_HEADERS)
            admin_endpoint = client.get("/api/admin/users", headers=AUTH_HEADERS)
            service_endpoint = client.get("/api/service/health", headers=AUTH_HEADERS)
    finally:
        app.dependency_overrides.clear()

    assert user_endpoint.status_code == 401
    assert admin_endpoint.status_code == 401
    assert service_endpoint.status_code == 200
    assert fake_database.audit_events[0].action == "service_token.used"


def test_user_data_is_owner_scoped_and_admin_endpoints_can_see_legacy_rows() -> None:
    fake_database = FakeAuthDatabase()
    app.dependency_overrides[get_database] = lambda: fake_database
    try:
        with TestClient(app) as client:
            user_a, _ = _register_session(
                client,
                fake_database,
                email="a@example.com",
            )
            run_a = _sample_run(user_a)
            legacy_run = _sample_run(None)
            fake_database.runs[run_a.run_id] = run_a
            fake_database.runs[legacy_run.run_id] = legacy_run
            fake_database.memories.append(
                MemoryItem(
                    id=str(uuid4()),
                    owner_user_id=user_a,
                    title="A memory",
                    category="general",
                    content="Private to user A.",
                    enabled=True,
                    created_at="2026-05-31T00:00:00+00:00",
                )
            )
            fake_database.memories.append(
                MemoryItem(
                    id=str(uuid4()),
                    owner_user_id=None,
                    title="Legacy",
                    category="general",
                    content="Ownerless legacy memory.",
                    enabled=True,
                    created_at="2026-05-31T00:00:00+00:00",
                )
            )

            own_run = client.get(f"/api/runs/{run_a.run_id}")
            own_memories = client.get("/api/memories")

            user_b, _ = _register_session(
                client,
                fake_database,
                email="b@example.com",
            )
            other_run = client.get(f"/api/runs/{run_a.run_id}")
            hidden_legacy_run = client.get(f"/api/runs/{legacy_run.run_id}")
            user_b_memories = client.get("/api/memories")

            fake_database.users[user_b]["role"] = "admin"
            admin_runs = client.get("/api/admin/runs")
            admin_memories = client.get("/api/admin/memories")
    finally:
        app.dependency_overrides.clear()

    assert own_run.status_code == 200
    assert own_memories.status_code == 200
    assert len(own_memories.json()) == 1
    assert other_run.status_code == 404
    assert hidden_legacy_run.status_code == 404
    assert user_b_memories.status_code == 200
    assert user_b_memories.json() == []
    assert admin_runs.status_code == 200
    assert {item["run_id"] for item in admin_runs.json()} == {
        run_a.run_id,
        legacy_run.run_id,
    }
    assert admin_memories.status_code == 200
    assert len(admin_memories.json()) == 2


def test_run_detail_rejects_invalid_uuid_path() -> None:
    with TestClient(app) as client:
        response = client.get("/api/runs/not-a-uuid")

    assert response.status_code == 422


def test_plan_request_rejects_oversized_memory_id_list() -> None:
    fake_database = FakeAuthDatabase()
    app.dependency_overrides[get_database] = lambda: fake_database
    try:
        with TestClient(app) as client:
            _, csrf_token = _register_session(client, fake_database)
            response = client.post(
                "/api/plans",
                headers={"X-CSRF-Token": csrf_token},
                json={
                    "task": "Create a short support workflow.",
                    "memory_ids": [str(uuid4()) for _ in range(26)],
                    "agent_profiles": [],
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422


def test_production_security_guard_rejects_missing_api_token() -> None:
    production_settings = Settings(
        APP_ENV="production",
        ORBIS_API_TOKEN="",
        DATABASE_AUTO_CREATE_TABLES=False,
        DATABASE_SSL="require",
        FRONTEND_ORIGINS="https://orbis.example.com",
        FRONTEND_ORIGIN="",
        SESSION_COOKIE_SECURE=True,
    )

    with pytest.raises(RuntimeError, match="ORBIS_API_TOKEN"):
        production_settings.validate_security_settings()


def test_production_security_guard_accepts_supabase_pooler_ssl_mode() -> None:
    production_settings = Settings(
        APP_ENV="production",
        ORBIS_API_TOKEN="test-token",
        DATABASE_AUTO_CREATE_TABLES=False,
        DATABASE_SSL="insecure-require",
        FRONTEND_ORIGINS="https://orbis.example.com",
        FRONTEND_ORIGIN="",
        SESSION_COOKIE_SECURE=True,
    )

    production_settings.validate_security_settings()


def test_production_security_guard_rejects_disabled_database_ssl() -> None:
    production_settings = Settings(
        APP_ENV="production",
        ORBIS_API_TOKEN="test-token",
        DATABASE_AUTO_CREATE_TABLES=False,
        DATABASE_SSL="disabled",
        FRONTEND_ORIGINS="https://orbis.example.com",
        FRONTEND_ORIGIN="",
        SESSION_COOKIE_SECURE=True,
    )

    with pytest.raises(RuntimeError, match="Encrypted DATABASE_SSL"):
        production_settings.validate_security_settings()


def test_production_security_guard_rejects_optional_database() -> None:
    production_settings = Settings(
        APP_ENV="production",
        ORBIS_API_TOKEN="test-token",
        DATABASE_REQUIRED=False,
        DATABASE_AUTO_CREATE_TABLES=False,
        DATABASE_SSL="require",
        FRONTEND_ORIGINS="https://orbis.example.com",
        FRONTEND_ORIGIN="",
        SESSION_COOKIE_SECURE=True,
    )

    with pytest.raises(RuntimeError, match="DATABASE_REQUIRED"):
        production_settings.validate_security_settings()
