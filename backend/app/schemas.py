from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field


AgentKind = Literal["supervisor", "worker"]
WorkerId = Literal["researcher", "strategist", "builder", "reviewer"]
WorkflowLogStatus = Literal["queued", "running", "completed", "failed", "cancelled"]
WorkflowRunStatus = Literal["queued", "running", "completed", "failed", "cancelled"]
OutputFormat = Literal["markdown", "json", "checklist", "table", "roadmap", "prd", "test_plan"]
ToolCallStatus = Literal["running", "completed", "failed"]
UserRole = Literal["admin", "guest", "vip"]
Identifier = Annotated[str, Field(min_length=1, max_length=80, pattern=r"^[a-zA-Z0-9_-]+$")]
NameText = Annotated[str, Field(min_length=1, max_length=120)]
ShortText = Annotated[str, Field(min_length=1, max_length=600)]
MediumText = Annotated[str, Field(min_length=1, max_length=1200)]
LongText = Annotated[str, Field(min_length=1, max_length=6000)]
EmailText = Annotated[
    str,
    Field(
        min_length=3,
        max_length=320,
        pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
    ),
]


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
    worker_id: WorkerId
    objective: ShortText
    expected_output: ShortText
    enabled: bool = True


class WorkerResult(BaseModel):
    worker_id: WorkerId
    worker_name: NameText
    objective: ShortText
    output: str


class AgentProfile(BaseModel):
    id: WorkerId
    name: NameText
    role: NameText
    goal: MediumText
    system_prompt: str = Field(default="", max_length=4000)
    model: str = Field(default="", max_length=160)
    temperature: float = Field(default=0.3, ge=0, le=2)
    max_tokens: int = Field(default=900, ge=128, le=8000)
    enabled: bool = True


class WorkflowTemplate(BaseModel):
    id: Identifier
    name: NameText
    description: MediumText
    task_prompt: LongText
    output_format: OutputFormat = "markdown"


class MemoryItem(BaseModel):
    id: str = Field(min_length=1, max_length=80)
    title: NameText
    category: str = Field(default="general", min_length=1, max_length=64)
    content: LongText
    enabled: bool = True
    created_at: str = ""


class MemoryCreateRequest(BaseModel):
    title: str = Field(min_length=2, max_length=120)
    category: str = Field(default="general", max_length=64)
    content: str = Field(min_length=3, max_length=6000)
    enabled: bool = True


class ToolCall(BaseModel):
    id: str = Field(min_length=1, max_length=80)
    run_id: str = Field(min_length=1, max_length=80)
    tool_name: str = Field(min_length=1, max_length=80)
    status: ToolCallStatus
    input: str = Field(max_length=2000)
    output: str = Field(max_length=6000)
    created_at: str


class EvaluationResult(BaseModel):
    id: str = Field(min_length=1, max_length=80)
    run_id: str = Field(min_length=1, max_length=80)
    rubric: str = Field(min_length=1, max_length=600)
    completeness: int = Field(ge=0, le=100)
    actionability: int = Field(ge=0, le=100)
    hallucination_risk: int = Field(ge=0, le=100)
    overall: int = Field(ge=0, le=100)
    notes: str = Field(max_length=2000)
    created_at: str


class WorkflowLog(BaseModel):
    run_id: str = Field(min_length=1, max_length=80)
    created_at: str
    agent_id: str = Field(min_length=1, max_length=80)
    agent_name: NameText
    status: WorkflowLogStatus
    message: str = Field(min_length=1, max_length=2000)


class PlanRequest(BaseModel):
    task: str = Field(min_length=3, max_length=4000)
    memory_ids: list[UUID] = Field(default_factory=list, max_length=25)
    agent_profiles: list[AgentProfile] = Field(default_factory=list, max_length=4)


class RunRequest(PlanRequest):
    plan: list[DelegationItem] | None = Field(default=None, max_length=4)
    output_format: OutputFormat = "markdown"
    enable_review_phase: bool = False


class WorkflowRun(BaseModel):
    run_id: str = Field(min_length=1, max_length=80)
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
    run_id: str = Field(min_length=1, max_length=80)
    task: str
    model: str
    status: str
    created_at: str
    completed_at: str


class RunDetail(WorkflowRun):
    evaluations: list[EvaluationResult] = Field(default_factory=list)


class RerunWorkerRequest(BaseModel):
    objective: ShortText | None = None
    expected_output: ShortText | None = None
    memory_ids: list[UUID] = Field(default_factory=list, max_length=25)
    agent_profiles: list[AgentProfile] = Field(default_factory=list, max_length=4)


class RerunSynthesisRequest(BaseModel):
    output_format: OutputFormat = "markdown"
    memory_ids: list[UUID] = Field(default_factory=list, max_length=25)


class EvaluationCompareRequest(BaseModel):
    run_ids: list[UUID] = Field(default_factory=list, min_length=1, max_length=10)
    rubric: str = Field(
        default="Completeness, actionability, risk awareness",
        min_length=3,
        max_length=600,
    )


class HealthResponse(BaseModel):
    status: str
    openrouter_configured: bool
    database_configured: bool
    database_status: str = "disabled"
    database_error_code: str = ""
    model: str


class AuthUser(BaseModel):
    id: str
    email: str
    display_name: str
    role: UserRole
    created_at: str


class RegisterRequest(BaseModel):
    email: EmailText
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(default="", max_length=120)


class LoginRequest(BaseModel):
    email: EmailText
    password: str = Field(min_length=1, max_length=128)


class SystemSettings(BaseModel):
    system_enabled: bool = True
    register_enabled: bool = True


class AuthResponse(BaseModel):
    token: str
    user: AuthUser
    system: SystemSettings


class SystemSettingsUpdate(BaseModel):
    system_enabled: bool | None = None
    register_enabled: bool | None = None


class AdminUser(AuthUser):
    is_active: bool = True
    updated_at: str


class UserRoleUpdateRequest(BaseModel):
    role: UserRole
    is_active: bool | None = None
