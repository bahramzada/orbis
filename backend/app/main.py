from contextlib import asynccontextmanager
import asyncio
import json
from typing import AsyncIterator

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from httpx import HTTPError

from app.agents import AgentOrchestrator, AgentRegistry
from app.config import get_settings
from app.openrouter_client import OpenRouterClient
from app.schemas import (
    AgentGraphResponse,
    HealthResponse,
    RunRequest,
    WorkflowLog,
    WorkflowRun,
)


registry = AgentRegistry()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    client = OpenRouterClient(settings)
    app.state.openrouter_client = client
    app.state.orchestrator = AgentOrchestrator(client, registry)
    yield
    await client.close()


app = FastAPI(title="Orbis API", version="0.1.0", lifespan=lifespan)
settings = get_settings()

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_orchestrator() -> AgentOrchestrator:
    return app.state.orchestrator


def get_client() -> OpenRouterClient:
    return app.state.openrouter_client


@app.get("/health", response_model=HealthResponse)
async def health(client: OpenRouterClient = Depends(get_client)) -> HealthResponse:
    return HealthResponse(
        status="ok",
        openrouter_configured=client.is_configured,
        model=client.model,
    )


@app.get("/api/agents", response_model=AgentGraphResponse)
async def get_agents() -> AgentGraphResponse:
    return registry.graph()


@app.post("/api/runs", response_model=WorkflowRun)
async def run_workflow(
    payload: RunRequest,
    orchestrator: AgentOrchestrator = Depends(get_orchestrator),
    client: OpenRouterClient = Depends(get_client),
) -> WorkflowRun:
    if not client.is_configured:
        raise HTTPException(
            status_code=503,
            detail="OPENROUTER_API_KEY is not configured.",
        )

    try:
        return await orchestrator.run(payload.task)
    except HTTPError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except (RuntimeError, ValueError, KeyError) as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/runs/stream")
async def stream_workflow(
    payload: RunRequest,
    orchestrator: AgentOrchestrator = Depends(get_orchestrator),
    client: OpenRouterClient = Depends(get_client),
) -> StreamingResponse:
    if not client.is_configured:
        raise HTTPException(
            status_code=503,
            detail="OPENROUTER_API_KEY is not configured.",
        )

    async def event_stream() -> AsyncIterator[str]:
        queue: asyncio.Queue[WorkflowLog | WorkflowRun | Exception | None] = (
            asyncio.Queue()
        )

        async def push_log(log: WorkflowLog) -> None:
            await queue.put(log)

        async def execute() -> None:
            try:
                result = await orchestrator.run(payload.task, log_callback=push_log)
                await queue.put(result)
            except Exception as exc:
                await queue.put(exc)
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
                elif isinstance(item, WorkflowRun):
                    yield _json_line("result", item.model_dump(mode="json"))
                else:
                    yield _json_line("error", {"detail": str(item)})
        finally:
            if not run_task.done():
                run_task.cancel()

    return StreamingResponse(event_stream(), media_type="application/x-ndjson")


def _json_line(event_type: str, payload: object) -> str:
    return json.dumps({"type": event_type, "payload": payload}) + "\n"
