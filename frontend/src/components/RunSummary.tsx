import { ChevronDown, Gauge, RotateCcw } from "lucide-react";

import { markdownInitialLineLimit } from "../constants";
import type { EvaluationResult, ToolCall, WorkflowRun } from "../types";
import { MarkdownContent } from "./MarkdownContent";

export function RunSummary({
  evaluations,
  run,
  toolCalls,
  onEvaluate,
  onRerunSynthesis,
  onRerunWorker
}: {
  evaluations: EvaluationResult[];
  run: WorkflowRun | null;
  toolCalls: ToolCall[];
  onEvaluate: () => void;
  onRerunSynthesis: () => void;
  onRerunWorker: (workerId: string) => void;
}) {
  if (!run) {
    return null;
  }

  return (
    <div className="run-summary">
      <RunInspector run={run} />
      <div className="inspector-actions">
        <button onClick={onEvaluate} type="button">
          <Gauge size={15} />
          Score
        </button>
        <button onClick={onRerunSynthesis} type="button">
          <RotateCcw size={15} />
          Rerun Final
        </button>
      </div>
      <EvaluationList evaluations={evaluations} />
      <ToolCallList toolCalls={toolCalls} />
      <PlanOutput run={run} />
      <h3>Worker Outputs</h3>
      {run.worker_results.map((result) => (
        <details className="worker-output" key={result.worker_id}>
          <summary>
            <span>{result.worker_name}</span>
            <span className="summary-meta">
              <button
                className="inline-action"
                onClick={(event) => {
                  event.preventDefault();
                  onRerunWorker(result.worker_id);
                }}
                type="button"
              >
                <RotateCcw size={14} />
              </button>
              <ChevronDown size={16} />
            </span>
          </summary>
          <MarkdownContent content={result.output} initialLineLimit={80} />
        </details>
      ))}
      <h3>Final</h3>
      <section className="final-output">
        <MarkdownContent
          content={run.final_answer}
          initialLineLimit={markdownInitialLineLimit}
        />
      </section>
    </div>
  );
}

function RunInspector({ run }: { run: WorkflowRun }) {
  return (
    <>
      <div className="model-pill">{run.model}</div>
      <div className="inspector-grid" aria-label="Run inspector">
        <span>
          <Gauge size={15} />
          {run.duration_ms ? `${(run.duration_ms / 1000).toFixed(1)}s` : "n/a"}
        </span>
        <span>{run.estimated_tokens || 0} est. tokens</span>
        <span title="Estimated as text-derived tokens x $0.0000015. Actual OpenRouter billing can differ.">
          ~${run.estimated_cost_usd.toFixed(6)} est.
        </span>
        <span>{run.output_format}</span>
      </div>
    </>
  );
}

function EvaluationList({ evaluations }: { evaluations: EvaluationResult[] }) {
  if (evaluations.length === 0) {
    return null;
  }

  return (
    <div className="evaluation-list">
      {evaluations.map((evaluation) => (
        <article key={evaluation.id}>
          <strong>{evaluation.overall}/100</strong>
          <span>
            complete {evaluation.completeness} · action {evaluation.actionability} · risk{" "}
            {evaluation.hallucination_risk}
          </span>
        </article>
      ))}
    </div>
  );
}

function ToolCallList({ toolCalls }: { toolCalls: ToolCall[] }) {
  if (toolCalls.length === 0) {
    return null;
  }

  return (
    <details className="plan-output">
      <summary>
        <span>Tool Calls</span>
        <span className="summary-meta">
          <small>{toolCalls.length} events</small>
          <ChevronDown size={16} />
        </span>
      </summary>
      {toolCalls.map((toolCall) => (
        <div className="result-row" key={toolCall.id}>
          <strong>{toolCall.tool_name}</strong>
          <span>{toolCall.output}</span>
        </div>
      ))}
    </details>
  );
}

function PlanOutput({ run }: { run: WorkflowRun }) {
  return (
    <details className="plan-output">
      <summary>
        <span>Plan</span>
        <span className="summary-meta">
          <small>{run.plan.length} agents</small>
          <ChevronDown size={16} />
        </span>
      </summary>
      {run.plan.map((item) => (
        <div className="result-row" key={item.worker_id}>
          <strong>{item.worker_id}</strong>
          <span>{item.objective}</span>
        </div>
      ))}
    </details>
  );
}
