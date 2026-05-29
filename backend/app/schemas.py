from typing import Literal

from pydantic import BaseModel, Field


AgentKind = Literal["supervisor", "worker"]
WorkflowLogStatus = Literal["running", "completed", "failed"]


class AgentNode(BaseModel):
    id: str
    name: str
    kind: AgentKind
    role: str
    goal: str
    x: int
    y: int


class AgentEdge(BaseModel):
    source: str
    target: str
    label: str


class AgentGraphResponse(BaseModel):
    agents: list[AgentNode]
    edges: list[AgentEdge]


class DelegationItem(BaseModel):
    worker_id: str
    objective: str
    expected_output: str


class WorkerResult(BaseModel):
    worker_id: str
    worker_name: str
    objective: str
    output: str


class WorkflowLog(BaseModel):
    created_at: str
    agent_id: str
    agent_name: str
    status: WorkflowLogStatus
    message: str


class RunRequest(BaseModel):
    task: str = Field(min_length=3, max_length=4000)


class WorkflowRun(BaseModel):
    task: str
    model: str
    logs: list[WorkflowLog]
    plan: list[DelegationItem]
    worker_results: list[WorkerResult]
    final_answer: str


class HealthResponse(BaseModel):
    status: str
    openrouter_configured: bool
    model: str
