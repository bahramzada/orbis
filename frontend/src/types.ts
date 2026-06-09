export type AgentKind = "supervisor" | "worker";

export type AgentNode = {
  id: string;
  name: string;
  kind: AgentKind;
  role: string;
  goal: string;
  x: number;
  y: number;
};

export type AgentEdge = {
  source: string;
  target: string;
  label: string;
};

export type AgentGraph = {
  agents: AgentNode[];
  edges: AgentEdge[];
};

export type DelegationItem = {
  worker_id: string;
  objective: string;
  expected_output: string;
  enabled: boolean;
};

export type WorkerResult = {
  worker_id: string;
  worker_name: string;
  objective: string;
  output: string;
};

export type WorkflowLogStatus =
  | "queued"
  | "running"
  | "completed"
  | "failed"
  | "cancelled";
export type WorkflowRunStatus =
  | "queued"
  | "running"
  | "completed"
  | "failed"
  | "cancelled";

export type OutputFormat =
  | "markdown"
  | "json"
  | "checklist"
  | "table"
  | "roadmap"
  | "prd"
  | "test_plan";

export type WorkflowLog = {
  run_id: string;
  created_at: string;
  agent_id: string;
  agent_name: string;
  status: WorkflowLogStatus;
  message: string;
};

export type WorkflowRun = {
  run_id: string;
  owner_user_id?: string | null;
  task: string;
  model: string;
  status: WorkflowRunStatus;
  logs: WorkflowLog[];
  plan: DelegationItem[];
  worker_results: WorkerResult[];
  final_answer: string;
  tool_calls: ToolCall[];
  output_format: OutputFormat;
  duration_ms: number;
  estimated_tokens: number;
  estimated_cost_usd: number;
};

export type WorkflowRunSummary = {
  run_id: string;
  task: string;
  model: string;
  status: string;
  created_at: string;
  completed_at: string;
  owner_user_id?: string | null;
};

export type AgentProfile = {
  id: string;
  name: string;
  role: string;
  goal: string;
  system_prompt: string;
  model: string;
  temperature: number;
  max_tokens: number;
  enabled: boolean;
};

export type WorkflowTemplate = {
  id: string;
  name: string;
  description: string;
  task_prompt: string;
  output_format: OutputFormat;
};

export type MemoryItem = {
  id: string;
  owner_user_id?: string | null;
  title: string;
  category: string;
  content: string;
  enabled: boolean;
  created_at: string;
};

export type ToolCall = {
  id: string;
  run_id: string;
  tool_name: string;
  status: "running" | "completed" | "failed";
  input: string;
  output: string;
  created_at: string;
};

export type EvaluationResult = {
  id: string;
  run_id: string;
  rubric: string;
  completeness: number;
  actionability: number;
  hallucination_risk: number;
  overall: number;
  notes: string;
  created_at: string;
};

export type RunDetail = WorkflowRun & {
  evaluations: EvaluationResult[];
};

export type RunOptions = {
  memory_ids?: string[];
  agent_profiles?: AgentProfile[];
  plan?: DelegationItem[] | null;
  output_format?: OutputFormat;
  enable_review_phase?: boolean;
};

export type UserRole = "admin" | "guest" | "vip";

export type AuthUser = {
  id: string;
  email: string;
  display_name: string;
  role: UserRole;
  created_at: string;
};

export type AdminUser = AuthUser & {
  is_active: boolean;
  updated_at: string;
};

export type SystemSettings = {
  system_enabled: boolean;
  register_enabled: boolean;
};

export type AdminHealthResponse = {
  status: string;
  openrouter_configured: boolean;
  database_configured: boolean;
  database_status: string;
  database_error_code: string;
  model: string;
};

export type AuditEvent = {
  id: string;
  actor_user_id?: string | null;
  actor_email: string;
  actor_role: string;
  action: string;
  resource_type: string;
  resource_id: string;
  ip_address: string;
  user_agent: string;
  detail: Record<string, unknown>;
  created_at: string;
};

export type AuthResponse = {
  token: string;
  csrf_token: string;
  user: AuthUser;
  system: SystemSettings;
};
