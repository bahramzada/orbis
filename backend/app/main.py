from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from httpx import HTTPError

from app.agents import AgentOrchestrator, AgentRegistry
from app.config import get_settings
from app.openrouter_client import OpenRouterClient
from app.schemas import AgentGraphResponse, HealthResponse, RunRequest, WorkflowRun


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
