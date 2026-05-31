import type {
  AgentGraph,
  AgentProfile,
  AdminUser,
  AuthResponse,
  DelegationItem,
  EvaluationResult,
  MemoryItem,
  OutputFormat,
  RunDetail,
  RunOptions,
  ToolCall,
  WorkflowLog,
  WorkflowRun,
  WorkflowTemplate
} from "./types";

const runtimeConfig = window.__ORBIS_CONFIG__ ?? {};
const apiBaseUrl =
  runtimeConfig.apiBaseUrl || import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";
const apiToken = runtimeConfig.apiToken || import.meta.env.VITE_ORBIS_API_TOKEN || "";
const authTokenStorageKey = "orbis_auth_token";

function authHeaders(): HeadersInit {
  const token = getAuthToken() || apiToken;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

function jsonHeaders(): HeadersInit {
  return {
    "Content-Type": "application/json",
    ...authHeaders()
  };
}

export function getAuthToken(): string {
  return window.localStorage.getItem(authTokenStorageKey) ?? "";
}

export function setAuthToken(token: string): void {
  window.localStorage.setItem(authTokenStorageKey, token);
}

export function clearAuthToken(): void {
  window.localStorage.removeItem(authTokenStorageKey);
}

export function hasConfiguredApiToken(): boolean {
  return Boolean(apiToken);
}

export async function registerUser(payload: {
  email: string;
  password: string;
  display_name: string;
}): Promise<AuthResponse> {
  const response = await fetch(`${apiBaseUrl}/api/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  if (!response.ok) {
    const error = (await response.json().catch(() => null)) as { detail?: string } | null;
    throw new Error(error?.detail ?? "Registration failed.");
  }
  return response.json() as Promise<AuthResponse>;
}

export async function loginUser(payload: {
  email: string;
  password: string;
}): Promise<AuthResponse> {
  const response = await fetch(`${apiBaseUrl}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  if (!response.ok) {
    const error = (await response.json().catch(() => null)) as { detail?: string } | null;
    throw new Error(error?.detail ?? "Login failed.");
  }
  return response.json() as Promise<AuthResponse>;
}

export async function fetchCurrentAuth(): Promise<AuthResponse> {
  const response = await fetch(`${apiBaseUrl}/api/auth/me`, {
    headers: authHeaders()
  });
  if (!response.ok) {
    throw new Error("Session could not be loaded.");
  }
  return response.json() as Promise<AuthResponse>;
}

export async function logoutUser(): Promise<void> {
  await fetch(`${apiBaseUrl}/api/auth/logout`, {
    method: "POST",
    headers: authHeaders()
  }).catch(() => undefined);
  clearAuthToken();
}

export async function fetchAdminUsers(): Promise<AdminUser[]> {
  const response = await fetch(`${apiBaseUrl}/api/admin/users`, {
    headers: authHeaders()
  });
  if (!response.ok) {
    throw new Error("Users could not be loaded.");
  }
  return response.json() as Promise<AdminUser[]>;
}

export async function updateAdminUser(
  userId: string,
  payload: { role: string; is_active?: boolean }
): Promise<AdminUser> {
  const response = await fetch(`${apiBaseUrl}/api/admin/users/${userId}`, {
    method: "PATCH",
    headers: jsonHeaders(),
    body: JSON.stringify(payload)
  });
  if (!response.ok) {
    throw new Error("User could not be updated.");
  }
  return response.json() as Promise<AdminUser>;
}

export async function updateSystemSettings(payload: {
  system_enabled?: boolean;
  register_enabled?: boolean;
}): Promise<AuthResponse["system"]> {
  const response = await fetch(`${apiBaseUrl}/api/admin/settings`, {
    method: "PATCH",
    headers: jsonHeaders(),
    body: JSON.stringify(payload)
  });
  if (!response.ok) {
    throw new Error("System settings could not be saved.");
  }
  return response.json() as Promise<AuthResponse["system"]>;
}

export const fallbackGraph: AgentGraph = {
  agents: [
    {
      id: "supervisor",
      name: "Supervisor",
      kind: "supervisor",
      role: "Coordinator",
      goal: "Breaks goals into worker tasks and synthesizes results.",
      x: 50,
      y: 12
    },
    {
      id: "researcher",
      name: "Researcher",
      kind: "worker",
      role: "Discovery",
      goal: "Collects context, assumptions, risks, and missing facts.",
      x: 18,
      y: 48
    },
    {
      id: "strategist",
      name: "Strategist",
      kind: "worker",
      role: "Planning",
      goal: "Turns context into an actionable approach.",
      x: 38,
      y: 72
    },
    {
      id: "builder",
      name: "Builder",
      kind: "worker",
      role: "Execution",
      goal: "Designs implementation and integration details.",
      x: 62,
      y: 72
    },
    {
      id: "reviewer",
      name: "Reviewer",
      kind: "worker",
      role: "Quality",
      goal: "Finds gaps, edge cases, and verification needs.",
      x: 82,
      y: 48
    }
  ],
  edges: [
    { source: "supervisor", target: "researcher", label: "delegates" },
    { source: "supervisor", target: "strategist", label: "delegates" },
    { source: "supervisor", target: "builder", label: "delegates" },
    { source: "supervisor", target: "reviewer", label: "delegates" }
  ]
};

export async function fetchAgents(): Promise<AgentGraph> {
  const response = await fetch(`${apiBaseUrl}/api/agents`, {
    headers: authHeaders()
  });
  if (!response.ok) {
    throw new Error("Agent graph could not be loaded.");
  }
  return response.json() as Promise<AgentGraph>;
}

export async function runWorkflow(
  task: string,
  options: RunOptions = {}
): Promise<WorkflowRun> {
  const response = await fetch(`${apiBaseUrl}/api/runs`, {
    method: "POST",
    headers: jsonHeaders(),
    body: JSON.stringify({ task, ...options })
  });

  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
    throw new Error(payload?.detail ?? "Workflow could not be completed.");
  }

  return response.json() as Promise<WorkflowRun>;
}

type WorkflowStreamEvent =
  | { type: "log"; payload: WorkflowLog }
  | { type: "tool_call"; payload: ToolCall }
  | { type: "result"; payload: WorkflowRun }
  | { type: "error"; payload: { detail?: string } };

export async function runWorkflowStream(
  task: string,
  onLog: (log: WorkflowLog) => void,
  signal?: AbortSignal,
  options: RunOptions = {},
  onToolCall?: (toolCall: ToolCall) => void
): Promise<WorkflowRun> {
  const response = await fetch(`${apiBaseUrl}/api/runs/stream`, {
    method: "POST",
    headers: jsonHeaders(),
    body: JSON.stringify({ task, ...options }),
    signal
  });

  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
    throw new Error(payload?.detail ?? "Workflow could not be started.");
  }

  if (!response.body) {
    return runWorkflow(task, options);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let finalRun: WorkflowRun | null = null;

  function consumeLine(line: string): void {
    if (!line.trim()) {
      return;
    }

    let event: WorkflowStreamEvent;
    try {
      event = JSON.parse(line) as WorkflowStreamEvent;
    } catch {
      throw new Error("Workflow stream returned malformed data.");
    }
    if (event.type === "log") {
      onLog(event.payload);
      return;
    }
    if (event.type === "tool_call") {
      onToolCall?.(event.payload);
      return;
    }
    if (event.type === "result") {
      finalRun = event.payload;
      return;
    }

    throw new Error(event.payload.detail ?? "Workflow failed.");
  }

  while (true) {
    const { done, value } = await reader.read();
    if (value) {
      buffer += decoder.decode(value, { stream: !done });
      const lines = buffer.split("\n");
      buffer = lines.pop() ?? "";
      lines.forEach(consumeLine);
    }
    if (done) {
      break;
    }
  }

  buffer += decoder.decode();
  consumeLine(buffer);

  if (!finalRun) {
    throw new Error("Workflow finished without a result.");
  }

  return finalRun;
}

export async function fetchAgentProfiles(): Promise<AgentProfile[]> {
  const response = await fetch(`${apiBaseUrl}/api/agent-profiles`, {
    headers: authHeaders()
  });
  if (!response.ok) {
    throw new Error("Agent profiles could not be loaded.");
  }
  return response.json() as Promise<AgentProfile[]>;
}

export async function saveAgentProfiles(
  profiles: AgentProfile[]
): Promise<AgentProfile[]> {
  const response = await fetch(`${apiBaseUrl}/api/agent-profiles`, {
    method: "PUT",
    headers: jsonHeaders(),
    body: JSON.stringify(profiles)
  });
  if (!response.ok) {
    throw new Error("Agent profiles could not be saved.");
  }
  return response.json() as Promise<AgentProfile[]>;
}

export async function fetchTemplates(): Promise<WorkflowTemplate[]> {
  const response = await fetch(`${apiBaseUrl}/api/templates`, {
    headers: authHeaders()
  });
  if (!response.ok) {
    throw new Error("Templates could not be loaded.");
  }
  return response.json() as Promise<WorkflowTemplate[]>;
}

export async function fetchMemories(): Promise<MemoryItem[]> {
  const response = await fetch(`${apiBaseUrl}/api/memories`, {
    headers: authHeaders()
  });
  if (!response.ok) {
    throw new Error("Memory items could not be loaded.");
  }
  return response.json() as Promise<MemoryItem[]>;
}

export async function createMemory(payload: {
  title: string;
  category: string;
  content: string;
  enabled: boolean;
}): Promise<MemoryItem> {
  const response = await fetch(`${apiBaseUrl}/api/memories`, {
    method: "POST",
    headers: jsonHeaders(),
    body: JSON.stringify(payload)
  });
  if (!response.ok) {
    throw new Error("Memory item could not be created.");
  }
  return response.json() as Promise<MemoryItem>;
}

export async function previewPlan(
  task: string,
  memoryIds: string[],
  agentProfiles: AgentProfile[]
): Promise<DelegationItem[]> {
  const response = await fetch(`${apiBaseUrl}/api/plans`, {
    method: "POST",
    headers: jsonHeaders(),
    body: JSON.stringify({
      task,
      memory_ids: memoryIds,
      agent_profiles: agentProfiles
    })
  });
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
    throw new Error(payload?.detail ?? "Plan could not be created.");
  }
  return response.json() as Promise<DelegationItem[]>;
}

export async function fetchRunDetail(runId: string): Promise<RunDetail> {
  const response = await fetch(`${apiBaseUrl}/api/runs/${runId}`, {
    headers: authHeaders()
  });
  if (!response.ok) {
    throw new Error("Run detail could not be loaded.");
  }
  return response.json() as Promise<RunDetail>;
}

export async function rerunWorker(
  runId: string,
  workerId: string,
  options: {
    objective?: string;
    expected_output?: string;
    memory_ids?: string[];
    agent_profiles?: AgentProfile[];
  }
): Promise<RunDetail> {
  const response = await fetch(`${apiBaseUrl}/api/runs/${runId}/rerun/worker/${workerId}`, {
    method: "POST",
    headers: jsonHeaders(),
    body: JSON.stringify(options)
  });
  if (!response.ok) {
    throw new Error("Worker rerun failed.");
  }
  return response.json() as Promise<RunDetail>;
}

export async function rerunSynthesis(
  runId: string,
  outputFormat: OutputFormat,
  memoryIds: string[]
): Promise<RunDetail> {
  const response = await fetch(`${apiBaseUrl}/api/runs/${runId}/rerun/synthesis`, {
    method: "POST",
    headers: jsonHeaders(),
    body: JSON.stringify({
      output_format: outputFormat,
      memory_ids: memoryIds
    })
  });
  if (!response.ok) {
    throw new Error("Synthesis rerun failed.");
  }
  return response.json() as Promise<RunDetail>;
}

export async function compareEvaluations(
  runIds: string[],
  rubric = "Completeness, actionability, hallucination risk"
): Promise<EvaluationResult[]> {
  const response = await fetch(`${apiBaseUrl}/api/evaluations/compare`, {
    method: "POST",
    headers: jsonHeaders(),
    body: JSON.stringify({
      run_ids: runIds,
      rubric
    })
  });
  if (!response.ok) {
    throw new Error("Evaluation compare failed.");
  }
  return response.json() as Promise<EvaluationResult[]>;
}
