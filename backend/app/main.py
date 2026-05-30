from contextlib import asynccontextmanager, suppress
import asyncio
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
import json
import logging
import secrets
from time import perf_counter
from typing import AsyncIterator, cast
from uuid import UUID, uuid4

from fastapi import Body, Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, StreamingResponse
from httpx import HTTPError
from starlette import status

from app.agents import AgentOrchestrator, AgentRegistry, WORKERS
from app.config import get_settings
from app.db import DatabaseRepository
from app.metrics import metrics
from app.openrouter_client import OpenRouterClient
from app.schemas import (
    AgentGraphResponse,
    AgentProfile,
    DelegationItem,
    EvaluationCompareRequest,
    EvaluationResult,
    HealthResponse,
    MemoryCreateRequest,
    MemoryItem,
    PlanRequest,
    RerunSynthesisRequest,
    RerunWorkerRequest,
    RunDetail,
    RunRequest,
    ToolCall,
    WorkerId,
    WorkflowTemplate,
    WorkflowLog,
    WorkflowRun,
    WorkflowRunSummary,
    WorkerResult,
)


registry = AgentRegistry()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level.upper())
    settings.validate_security_settings()
    client = OpenRouterClient(settings)
    database = DatabaseRepository(settings)
    await database.init()
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
    allow_methods=["GET", "POST", "PUT", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
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


def get_orchestrator() -> AgentOrchestrator:
    return app.state.orchestrator


def get_client() -> OpenRouterClient:
    return app.state.openrouter_client


def get_database() -> DatabaseRepository:
    return app.state.database


class StreamError:
    def __init__(self, detail: str) -> None:
        self.detail = detail


def require_api_token(authorization: str = Header(default="")) -> None:
    expected = settings.orbis_api_token.strip()
    if not expected and not settings.is_production:
        return
    if not expected or not _is_authorized(authorization, expected):
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
    scheme, _, token = authorization.partition(" ")
    return (
        scheme.lower() == "bearer"
        and bool(token)
        and secrets.compare_digest(token, expected_token)
    )


@app.get("/health", response_model=HealthResponse)
async def health(
    client: OpenRouterClient = Depends(get_client),
    database: DatabaseRepository = Depends(get_database),
) -> HealthResponse:
    return HealthResponse(
        status="ok",
        openrouter_configured=client.is_configured,
        database_configured=database.is_configured,
        model=client.model,
    )


@app.get("/metrics")
async def get_metrics(_: None = Depends(require_metrics_token)) -> PlainTextResponse:
    if not settings.enable_metrics:
        raise HTTPException(status_code=404, detail="Metrics are disabled.")
    return PlainTextResponse(metrics.render_prometheus(), media_type="text/plain")


@app.get("/api/agents", response_model=AgentGraphResponse)
async def get_agents() -> AgentGraphResponse:
    return registry.graph()


@app.post("/api/runs", response_model=WorkflowRun)
async def run_workflow(
    payload: RunRequest,
    _: None = Depends(require_api_token),
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
    _: None = Depends(require_api_token),
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
    _: None = Depends(require_api_token),
    database: DatabaseRepository = Depends(get_database),
) -> list[AgentProfile]:
    normalized = _profiles_or_defaults(profiles)
    app.state.agent_profiles = normalized
    await database.save_agent_profiles(normalized)
    return normalized


@app.get("/api/templates", response_model=list[WorkflowTemplate])
async def list_templates(
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
    _: None = Depends(require_api_token),
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
    _: None = Depends(require_api_token),
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
    _: None = Depends(require_api_token),
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
    _: None = Depends(require_api_token),
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
    _: None = Depends(require_api_token),
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
