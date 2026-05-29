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

export type WorkflowRun = {
  task: string;
  model: string;
  plan: DelegationItem[];
  worker_results: WorkerResult[];
  final_answer: string;
};
