import type { ReactNode } from "react";
import { useEffect, useMemo, useState } from "react";
import {
  Activity,
  AlertTriangle,
  Building2,
  BrainCircuit,
  CheckCircle2,
  ChevronDown,
  Loader2,
  Network,
  Play,
  Users
} from "lucide-react";

import { fallbackGraph, fetchAgents, runWorkflowStream } from "./api";
import type { AgentGraph, AgentNode, WorkflowLog, WorkflowRun } from "./types";

type ViewMode = "visual" | "office";
type RunState = "idle" | "running" | "success" | "error";

const starterTask =
  "Design a customer support automation flow for a small SaaS team.";

const visualPositionOverrides: Record<string, Pick<AgentNode, "x" | "y">> = {
  supervisor: { x: 50, y: 16 },
  researcher: { x: 24, y: 50 },
  strategist: { x: 32, y: 70 },
  builder: { x: 68, y: 70 },
  reviewer: { x: 76, y: 50 }
};

function App() {
  const [graph, setGraph] = useState<AgentGraph>(fallbackGraph);
  const [mode, setMode] = useState<ViewMode>("visual");
  const [task, setTask] = useState(starterTask);
  const [run, setRun] = useState<WorkflowRun | null>(null);
  const [logs, setLogs] = useState<WorkflowLog[]>([]);
  const [error, setError] = useState("");
  const [runState, setRunState] = useState<RunState>("idle");
  const isRunning = runState === "running";

  const supervisor = useMemo(
    () => graph.agents.find((agent) => agent.kind === "supervisor"),
    [graph.agents]
  );
  const workers = useMemo(
    () => graph.agents.filter((agent) => agent.kind === "worker"),
    [graph.agents]
  );

  useEffect(() => {
    fetchAgents()
      .then(setGraph)
      .catch(() => setGraph(fallbackGraph));
  }, []);

  useEffect(() => {
    if (runState !== "success") {
      return undefined;
    }

    const timeout = window.setTimeout(() => setRunState("idle"), 2200);
    return () => window.clearTimeout(timeout);
  }, [runState]);

  function handleTaskChange(value: string) {
    setTask(value);
    if (!isRunning) {
      setError("");
      setRunState("idle");
    }
  }

  async function handleRun() {
    setError("");
    setRun(null);
    setLogs([]);
    setRunState("running");
    try {
      const result = await runWorkflowStream(task, (log) => {
        setLogs((currentLogs) => [...currentLogs, log]);
      });
      setRun(result);
      setLogs(result.logs);
      setRunState("success");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Workflow failed.");
      setRunState("error");
    }
  }

  const runButtonLabel =
    runState === "running"
      ? "Running"
      : runState === "success"
        ? "Completed"
        : runState === "error"
          ? "Retry"
          : "Run";

  const runButtonIcon =
    runState === "running" ? (
      <Loader2 className="spin" size={18} />
    ) : runState === "success" ? (
      <CheckCircle2 size={18} />
    ) : runState === "error" ? (
      <AlertTriangle size={18} />
    ) : (
      <Play size={18} />
    );

  return (
    <main className="app-shell">
      <section className="topbar">
        <div>
          <p className="eyebrow">Orbis</p>
          <h1>Agent Control Room</h1>
        </div>
        <div className="toolbar" aria-label="View mode">
          <button
            className={mode === "visual" ? "active" : ""}
            onClick={() => setMode("visual")}
            title="Simple visual management"
            type="button"
          >
            <Network size={18} />
            Visual
          </button>
          <button
            className={mode === "office" ? "active" : ""}
            onClick={() => setMode("office")}
            title="Office management"
            type="button"
          >
            <Building2 size={18} />
            Office
          </button>
        </div>
      </section>

      <section className="workspace">
        <div className="graph-panel">
          {mode === "visual" ? (
            <VisualGraph graph={graph} />
          ) : (
            <OfficeGraph supervisor={supervisor} workers={workers} />
          )}
        </div>

        <aside className="control-panel">
          <div className="panel-header">
            <div>
              <p className="eyebrow">Workflow</p>
              <h2>Supervisor Run</h2>
            </div>
            <BrainCircuit size={24} />
          </div>

          <label className="task-box">
            <span>Task</span>
            <textarea
              value={task}
              onChange={(event) => handleTaskChange(event.currentTarget.value)}
            />
            <span className="task-helper">
              <span>{task.trim().length}/4000</span>
              <span>{isRunning ? "Workflow active" : run ? "Last run ready" : "No run yet"}</span>
            </span>
          </label>

          <button
            className={`run-button ${runState}`}
            disabled={isRunning || task.trim().length < 3}
            onClick={handleRun}
            type="button"
          >
            {runButtonIcon}
            {runButtonLabel}
          </button>

          {error ? <div className="error-box">{error}</div> : null}
          <ActivityLog logs={run?.logs.length ? run.logs : logs} isRunning={isRunning} />
          <RunSummary run={run} />
        </aside>
      </section>
    </main>
  );
}

function VisualGraph({ graph }: { graph: AgentGraph }) {
  const displayAgents = graph.agents.map((agent) => ({
    ...agent,
    ...(visualPositionOverrides[agent.id] ?? {})
  }));

  return (
    <div className="visual-canvas">
      {graph.edges.map((edge) => {
        const source = displayAgents.find((agent) => agent.id === edge.source);
        const target = displayAgents.find((agent) => agent.id === edge.target);
        if (!source || !target) {
          return null;
        }

        return (
          <ConnectionLine
            key={`${edge.source}-${edge.target}`}
            source={source}
            target={target}
          />
        );
      })}

      {displayAgents.map((agent) => (
        <AgentBadge key={agent.id} agent={agent} />
      ))}
    </div>
  );
}

function ConnectionLine({ source, target }: { source: AgentNode; target: AgentNode }) {
  const x1 = source.x;
  const y1 = source.y + 7;
  const x2 = target.x;
  const y2 = target.y - 7;
  const length = Math.hypot(x2 - x1, y2 - y1);
  const angle = (Math.atan2(y2 - y1, x2 - x1) * 180) / Math.PI;

  return (
    <span
      className="connection-line"
      style={{
        left: `${x1}%`,
        top: `${y1}%`,
        width: `${length}%`,
        transform: `rotate(${angle}deg)`
      }}
    />
  );
}

function AgentBadge({ agent }: { agent: AgentNode }) {
  return (
    <article
      className={`agent-badge ${agent.kind}`}
      style={{ left: `${agent.x}%`, top: `${agent.y}%` }}
    >
      <div className="agent-icon">{agent.kind === "supervisor" ? <Users /> : <Activity />}</div>
      <div>
        <strong>{agent.name}</strong>
        <span>{agent.role}</span>
      </div>
    </article>
  );
}

function OfficeGraph({
  supervisor,
  workers
}: {
  supervisor: AgentNode | undefined;
  workers: AgentNode[];
}) {
  const agents = [supervisor, ...workers].filter(Boolean) as AgentNode[];

  return (
    <div className="office-scene">
      <div className="office-floor">
        {agents.map((agent, index) => (
          <div
            className={`office-agent ${agent.kind}`}
            key={agent.id}
            style={{
              gridColumn: `${2 + (index % 3) * 2}`,
              gridRow: `${2 + Math.floor(index / 3) * 2}`
            }}
            title={agent.goal}
          >
            <div className="desk" />
            <div className="avatar">
              <span />
            </div>
            <strong>{agent.name}</strong>
            <small>{agent.role}</small>
          </div>
        ))}
      </div>
    </div>
  );
}

function ActivityLog({
  logs,
  isRunning
}: {
  logs: WorkflowLog[];
  isRunning: boolean;
}) {
  if (logs.length === 0) {
    return (
      <div className="empty-state">
        {isRunning ? <Loader2 className="spin" size={18} /> : <CheckCircle2 size={18} />}
        <span>{isRunning ? "Starting workflow" : "No run yet"}</span>
      </div>
    );
  }

  const latestLogIndexByAgent = new Map<string, number>();
  logs.forEach((log, index) => {
    latestLogIndexByAgent.set(log.agent_id, index);
  });

  return (
    <div className="activity-log">
      <div className="activity-heading">
        <strong>Agent Logs</strong>
        <span>{isRunning ? "Running" : "Done"}</span>
      </div>
      {logs
        .map((log, index) => ({ index, log }))
        .reverse()
        .map(({ index, log }) => {
          const isActiveLog =
            isRunning &&
            log.status === "running" &&
            latestLogIndexByAgent.get(log.agent_id) === index;

          return (
            <div
              className={`log-row ${log.status} ${isActiveLog ? "active" : "settled"}`}
              key={`${log.created_at}-${log.agent_id}-${index}`}
            >
              <LogStatusIcon status={log.status} isActive={isActiveLog} />
              <div>
                <div className="log-meta">
                  <strong>{log.agent_name}</strong>
                  <time>{formatLogTime(log.created_at)}</time>
                </div>
                <span>{log.message}</span>
              </div>
            </div>
          );
        })}
    </div>
  );
}

function LogStatusIcon({
  status,
  isActive
}: {
  status: WorkflowLog["status"];
  isActive: boolean;
}) {
  if (status === "completed") {
    return <CheckCircle2 size={17} />;
  }
  if (status === "failed") {
    return <AlertTriangle size={17} />;
  }
  if (isActive) {
    return <Loader2 className="spin" size={17} />;
  }
  return <Activity size={17} />;
}

function formatLogTime(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit"
  }).format(new Date(value));
}

function RunSummary({ run }: { run: WorkflowRun | null }) {
  if (!run) {
    return null;
  }

  return (
    <div className="run-summary">
      <div className="model-pill">{run.model}</div>
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
      <h3>Worker Outputs</h3>
      {run.worker_results.map((result) => (
        <details className="worker-output" key={result.worker_id}>
          <summary>
            <span>{result.worker_name}</span>
            <ChevronDown size={16} />
          </summary>
          <MarkdownContent content={result.output} />
        </details>
      ))}
      <h3>Final</h3>
      <section className="final-output">
        <MarkdownContent content={run.final_answer} />
      </section>
    </div>
  );
}

function MarkdownContent({ content }: { content: string }) {
  return (
    <div className="markdown-content">
      {content.split("\n").map((line, index) => {
        const trimmed = line.trim();
        if (!trimmed) {
          return null;
        }
        if (/^-{3,}$/.test(trimmed)) {
          return <hr key={`${index}-${trimmed}`} />;
        }
        if (trimmed.startsWith("### ")) {
          return <h5 key={`${index}-${trimmed}`}>{renderInlineMarkdown(trimmed.slice(4))}</h5>;
        }
        if (trimmed.startsWith("## ")) {
          return <h4 key={`${index}-${trimmed}`}>{renderInlineMarkdown(trimmed.slice(3))}</h4>;
        }
        if (trimmed.startsWith("# ")) {
          return <h4 key={`${index}-${trimmed}`}>{renderInlineMarkdown(trimmed.slice(2))}</h4>;
        }
        if (/^[-*]\s+/.test(trimmed)) {
          return (
            <p className="markdown-list-line" key={`${index}-${trimmed}`}>
              {renderInlineMarkdown(trimmed.replace(/^[-*]\s+/, ""))}
            </p>
          );
        }
        if (/^\d+\.\s+/.test(trimmed)) {
          return (
            <p className="markdown-list-line numbered" key={`${index}-${trimmed}`}>
              {renderInlineMarkdown(trimmed)}
            </p>
          );
        }
        if (trimmed.startsWith("|")) {
          return (
            <pre className="markdown-table-line" key={`${index}-${trimmed}`}>
              {trimmed}
            </pre>
          );
        }
        return <p key={`${index}-${trimmed}`}>{renderInlineMarkdown(trimmed)}</p>;
      })}
    </div>
  );
}

function renderInlineMarkdown(text: string): ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*)/g).map((part, index) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      return <strong key={`${index}-${part}`}>{part.slice(2, -2)}</strong>;
    }
    return part;
  });
}

export default App;
