import type {
  AgentGraph,
  AgentProfile,
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

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

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
  const response = await fetch(`${apiBaseUrl}/api/agents`);
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
    headers: {
      "Content-Type": "application/json"
    },
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
    headers: {
      "Content-Type": "application/json"
    },
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

    const event = JSON.parse(line) as WorkflowStreamEvent;
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
  const response = await fetch(`${apiBaseUrl}/api/agent-profiles`);
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
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify(profiles)
  });
  if (!response.ok) {
    throw new Error("Agent profiles could not be saved.");
  }
  return response.json() as Promise<AgentProfile[]>;
}

export async function fetchTemplates(): Promise<WorkflowTemplate[]> {
  const response = await fetch(`${apiBaseUrl}/api/templates`);
  if (!response.ok) {
    throw new Error("Templates could not be loaded.");
  }
  return response.json() as Promise<WorkflowTemplate[]>;
}

export async function fetchMemories(): Promise<MemoryItem[]> {
  const response = await fetch(`${apiBaseUrl}/api/memories`);
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
    headers: {
      "Content-Type": "application/json"
    },
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
    headers: {
      "Content-Type": "application/json"
    },
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
  const response = await fetch(`${apiBaseUrl}/api/runs/${runId}`);
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
    headers: {
      "Content-Type": "application/json"
    },
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
    headers: {
      "Content-Type": "application/json"
    },
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
    headers: {
      "Content-Type": "application/json"
    },
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
