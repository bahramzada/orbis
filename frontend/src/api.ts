import type { AgentGraph, WorkflowLog, WorkflowRun } from "./types";

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

export async function runWorkflow(task: string): Promise<WorkflowRun> {
  const response = await fetch(`${apiBaseUrl}/api/runs`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({ task })
  });

  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
    throw new Error(payload?.detail ?? "Workflow could not be completed.");
  }

  return response.json() as Promise<WorkflowRun>;
}

type WorkflowStreamEvent =
  | { type: "log"; payload: WorkflowLog }
  | { type: "result"; payload: WorkflowRun }
  | { type: "error"; payload: { detail?: string } };

export async function runWorkflowStream(
  task: string,
  onLog: (log: WorkflowLog) => void,
  signal?: AbortSignal
): Promise<WorkflowRun> {
  const response = await fetch(`${apiBaseUrl}/api/runs/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({ task }),
    signal
  });

  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
    throw new Error(payload?.detail ?? "Workflow could not be started.");
  }

  if (!response.body) {
    return runWorkflow(task);
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
