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
  task: string;
  model: string;
  status: WorkflowRunStatus;
  logs: WorkflowLog[];
  plan: DelegationItem[];
  worker_results: WorkerResult[];
  final_answer: string;
};
