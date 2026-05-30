import type { AgentNode, OutputFormat } from "./types";

export const starterTask =
  "Design a customer support automation flow for a small SaaS team.";

export const outputFormats: OutputFormat[] = [
  "markdown",
  "checklist",
  "roadmap",
  "table",
  "json",
  "prd",
  "test_plan"
];

export const visualPositionOverrides: Record<string, Pick<AgentNode, "x" | "y">> = {
  supervisor: { x: 50, y: 16 },
  researcher: { x: 24, y: 50 },
  strategist: { x: 32, y: 70 },
  builder: { x: 68, y: 70 },
  reviewer: { x: 76, y: 50 }
};

export const workerOrder = ["researcher", "strategist", "builder", "reviewer"];

export const officeAgentMeta: Record<
  string,
  { slot: string; label: string; bubble: string; progress: number }
> = {
  supervisor: {
    slot: "supervisor",
    label: "Supervisor",
    bubble: "Decompose",
    progress: 88
  },
  researcher: {
    slot: "researcher",
    label: "Worker 1",
    bubble: "Research",
    progress: 72
  },
  strategist: {
    slot: "strategist",
    label: "Worker 2",
    bubble: "Strategy",
    progress: 64
  },
  builder: {
    slot: "builder",
    label: "Worker 3",
    bubble: "Build",
    progress: 69
  },
  reviewer: {
    slot: "reviewer",
    label: "Worker 4",
    bubble: "Review",
    progress: 76
  }
};

export const logPreviewLimit = 80;
export const markdownInitialLineLimit = 140;
