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
  { slot: string; label: string; bubble: string }
> = {
  supervisor: {
    slot: "supervisor",
    label: "Supervisor",
    bubble: "Decompose"
  },
  researcher: {
    slot: "researcher",
    label: "Worker 1",
    bubble: "Research"
  },
  strategist: {
    slot: "strategist",
    label: "Worker 2",
    bubble: "Strategy"
  },
  builder: {
    slot: "builder",
    label: "Worker 3",
    bubble: "Build"
  },
  reviewer: {
    slot: "reviewer",
    label: "Worker 4",
    bubble: "Review"
  }
};

export const logPreviewLimit = 80;
export const markdownInitialLineLimit = 140;
