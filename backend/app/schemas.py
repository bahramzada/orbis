from typing import Literal

from pydantic import BaseModel, Field


AgentKind = Literal["supervisor", "worker"]
WorkflowLogStatus = Literal["queued", "running", "completed", "failed", "cancelled"]
WorkflowRunStatus = Literal["queued", "running", "completed", "failed", "cancelled"]
OutputFormat = Literal["markdown", "json", "checklist", "table", "roadmap", "prd", "test_plan"]
ToolCallStatus = Literal["running", "completed", "failed"]


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
    enabled: bool = True


class WorkerResult(BaseModel):
    worker_id: str
    worker_name: str
    objective: str
    output: str


class AgentProfile(BaseModel):
    id: str
    name: str
    role: str
    goal: str
    system_prompt: str = ""
    model: str = ""
    temperature: float = Field(default=0.3, ge=0, le=2)
    max_tokens: int = Field(default=900, ge=128, le=8000)
    enabled: bool = True


class WorkflowTemplate(BaseModel):
    id: str
    name: str
    description: str
    task_prompt: str
    output_format: OutputFormat = "markdown"


class MemoryItem(BaseModel):
    id: str
    title: str
    category: str = "general"
    content: str
    enabled: bool = True
    created_at: str = ""


class MemoryCreateRequest(BaseModel):
    title: str = Field(min_length=2, max_length=120)
    category: str = Field(default="general", max_length=64)
    content: str = Field(min_length=3, max_length=6000)
    enabled: bool = True


class ToolCall(BaseModel):
    id: str
    run_id: str
    tool_name: str
    status: ToolCallStatus
    input: str
    output: str
    created_at: str


class EvaluationResult(BaseModel):
    id: str
    run_id: str
    rubric: str
    completeness: int = Field(ge=0, le=100)
    actionability: int = Field(ge=0, le=100)
    hallucination_risk: int = Field(ge=0, le=100)
    overall: int = Field(ge=0, le=100)
    notes: str
    created_at: str


class WorkflowLog(BaseModel):
    run_id: str
    created_at: str
    agent_id: str
    agent_name: str
    status: WorkflowLogStatus
    message: str


class PlanRequest(BaseModel):
    task: str = Field(min_length=3, max_length=4000)
    memory_ids: list[str] = Field(default_factory=list)
    agent_profiles: list[AgentProfile] = Field(default_factory=list)


class RunRequest(PlanRequest):
    plan: list[DelegationItem] | None = None
    output_format: OutputFormat = "markdown"
    enable_review_phase: bool = False


class WorkflowRun(BaseModel):
    run_id: str
    task: str
    model: str
    status: WorkflowRunStatus = "completed"
    logs: list[WorkflowLog]
    plan: list[DelegationItem]
    worker_results: list[WorkerResult]
    final_answer: str
    tool_calls: list[ToolCall] = Field(default_factory=list)
    output_format: OutputFormat = "markdown"
    duration_ms: int = 0
    estimated_tokens: int = 0
    estimated_cost_usd: float = 0


class WorkflowRunSummary(BaseModel):
    run_id: str
    task: str
    model: str
    status: str
    created_at: str
    completed_at: str


class RunDetail(WorkflowRun):
    evaluations: list[EvaluationResult] = Field(default_factory=list)


class RerunWorkerRequest(BaseModel):
    objective: str | None = None
    expected_output: str | None = None
    memory_ids: list[str] = Field(default_factory=list)
    agent_profiles: list[AgentProfile] = Field(default_factory=list)


class RerunSynthesisRequest(BaseModel):
    output_format: OutputFormat = "markdown"
    memory_ids: list[str] = Field(default_factory=list)


class EvaluationCompareRequest(BaseModel):
    run_ids: list[str] = Field(default_factory=list)
    rubric: str = Field(default="Completeness, actionability, risk awareness")


class HealthResponse(BaseModel):
    status: str
    openrouter_configured: bool
    database_configured: bool
    model: str
