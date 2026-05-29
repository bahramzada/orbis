import type { CSSProperties, ReactNode } from "react";
import { useEffect, useMemo, useRef, useState } from "react";
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
  Users,
  XCircle
} from "lucide-react";

import { fallbackGraph, fetchAgents, runWorkflowStream } from "./api";
import type { AgentGraph, AgentNode, WorkflowLog, WorkflowRun } from "./types";

type ViewMode = "visual" | "office";
type RunState = "idle" | "running" | "success" | "error";

const starterTask =
  "Design a customer support automation flow for a small SaaS team.";
const logPreviewLimit = 80;
const markdownInitialLineLimit = 140;

const visualPositionOverrides: Record<string, Pick<AgentNode, "x" | "y">> = {
  supervisor: { x: 50, y: 16 },
  researcher: { x: 24, y: 50 },
  strategist: { x: 32, y: 70 },
  builder: { x: 68, y: 70 },
  reviewer: { x: 76, y: 50 }
};

const workerOrder = ["researcher", "strategist", "builder", "reviewer"];

const officeAgentMeta: Record<
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

function App() {
  const [graph, setGraph] = useState<AgentGraph>(fallbackGraph);
  const [mode, setMode] = useState<ViewMode>("visual");
  const [task, setTask] = useState(starterTask);
  const [run, setRun] = useState<WorkflowRun | null>(null);
  const [logs, setLogs] = useState<WorkflowLog[]>([]);
  const [error, setError] = useState("");
  const [runState, setRunState] = useState<RunState>("idle");
  const abortControllerRef = useRef<AbortController | null>(null);
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
    abortControllerRef.current?.abort();
    const controller = new AbortController();
    abortControllerRef.current = controller;
    setError("");
    setRun(null);
    setLogs([]);
    setRunState("running");
    try {
      const result = await runWorkflowStream(task, (log) => {
        setLogs((currentLogs) => [...currentLogs, log]);
      }, controller.signal);
      setRun(result);
      setLogs(result.logs);
      setRunState("success");
    } catch (caught) {
      if (caught instanceof DOMException && caught.name === "AbortError") {
        setRunState("idle");
      } else {
        setError(caught instanceof Error ? caught.message : "Workflow failed.");
        setRunState("error");
      }
    } finally {
      if (abortControllerRef.current === controller) {
        abortControllerRef.current = null;
      }
    }
  }

  function handleCancelRun() {
    abortControllerRef.current?.abort();
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

          <div className="run-actions">
            <button
              className={`run-button ${runState}`}
              disabled={isRunning || task.trim().length < 3}
              onClick={handleRun}
              type="button"
            >
              {runButtonIcon}
              {runButtonLabel}
            </button>
            {isRunning ? (
              <button className="cancel-button" onClick={handleCancelRun} type="button">
                <XCircle size={18} />
                Cancel
              </button>
            ) : null}
          </div>

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
  const orderedWorkers = [
    ...workerOrder
      .map((id) => workers.find((worker) => worker.id === id))
      .filter(Boolean),
    ...workers.filter((worker) => !workerOrder.includes(worker.id))
  ] as AgentNode[];
  const workerCount = orderedWorkers.length;

  return (
    <div className="office-scene">
      <div className="office-titlebar">
        <span>Agentic AI Office</span>
        <strong>1 Supervisor, {workerCount} Workers: Hierarchical AI System</strong>
      </div>
      <div className="office-stage">
        <div className="office-room">
          <div className="office-wall">
            <div className="office-board">
              <span>Supervisor 01</span>
              <b>Decompose &gt; Delegate &gt; Aggregate</b>
            </div>
            <div className="office-cabinet cabinet-a" />
            <div className="office-plant" />
          </div>

          <div className="office-floor">
            <svg
              aria-hidden="true"
              className="office-links"
              preserveAspectRatio="none"
              viewBox="0 0 100 100"
            >
              <path d="M50 45 L28 47" />
              <path d="M50 48 L37 63" />
              <path d="M50 48 L63 63" />
              <path d="M50 45 L72 47" />
            </svg>
            <div className="office-prop prop-water" />
            <div className="office-prop prop-files" />
            <div className="office-prop prop-server" />
            {supervisor ? <OfficeAgentStation agent={supervisor} /> : null}
            {orderedWorkers.map((agent) => (
              <OfficeAgentStation agent={agent} key={agent.id} />
            ))}
          </div>

          <aside className="office-status-card" aria-label="System status">
            <span>System Status</span>
            <strong>Operational</strong>
            <dl>
              <div>
                <dt>Active Task</dt>
                <dd>Supervisor workflow</dd>
              </div>
              <div>
                <dt>Tasks Assigned</dt>
                <dd>{workerCount}</dd>
              </div>
              <div>
                <dt>Progress</dt>
                <dd>Ready</dd>
              </div>
            </dl>
          </aside>
        </div>
      </div>
    </div>
  );
}

function OfficeAgentStation({ agent }: { agent: AgentNode }) {
  const meta =
    officeAgentMeta[agent.id] ??
    ({
      slot: "fallback",
      label: agent.kind === "supervisor" ? "Supervisor" : "Worker",
      bubble: agent.role,
      progress: 58
    } satisfies (typeof officeAgentMeta)[string]);
  const style = { "--progress": `${meta.progress}%` } as CSSProperties;

  return (
    <article
      className={`office-agent station-${meta.slot} ${agent.kind}`}
      style={style}
      title={agent.goal}
    >
      <div className="office-agent-label">{meta.label}</div>
      <div className="office-bubble">{meta.bubble}</div>
      <div className="office-desk">
        <div className="office-monitor" />
        <div className="office-keyboard" />
      </div>
      <div className="office-avatar">
        <span />
      </div>
      <div className="office-agent-copy">
        <strong>{agent.name}</strong>
        <small>{agent.role}</small>
      </div>
      <div className="office-progress" />
    </article>
  );
}

function ActivityLog({
  logs,
  isRunning
}: {
  logs: WorkflowLog[];
  isRunning: boolean;
}) {
  const [showAllLogs, setShowAllLogs] = useState(false);
  const latestLogIndexByAgent = useMemo(() => {
    const latest = new Map<string, number>();
    logs.forEach((log, index) => {
      latest.set(log.agent_id, index);
    });
    return latest;
  }, [logs]);
  const renderedLogs = useMemo(() => {
    const reversed = logs.map((log, index) => ({ index, log })).reverse();
    return showAllLogs ? reversed : reversed.slice(0, logPreviewLimit);
  }, [logs, showAllLogs]);
  const hiddenLogCount = Math.max(0, logs.length - renderedLogs.length);

  if (logs.length === 0) {
    return (
      <div className="empty-state">
        {isRunning ? <Loader2 className="spin" size={18} /> : <CheckCircle2 size={18} />}
        <span>{isRunning ? "Starting workflow" : "No run yet"}</span>
      </div>
    );
  }

  return (
    <div className="activity-log">
      <div className="activity-heading">
        <strong>Agent Logs</strong>
        <span>{isRunning ? "Running" : "Done"}</span>
      </div>
      {renderedLogs.map(({ index, log }) => {
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
      {hiddenLogCount > 0 ? (
        <button
          className="show-more-button"
          onClick={() => setShowAllLogs(true)}
          type="button"
        >
          Show {hiddenLogCount} older logs
        </button>
      ) : null}
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

function MarkdownContent({
  content,
  initialLineLimit = 0
}: {
  content: string;
  initialLineLimit?: number;
}) {
  const [isExpanded, setIsExpanded] = useState(false);
  const lines = useMemo(() => content.split("\n"), [content]);
  const visibleLines =
    initialLineLimit > 0 && !isExpanded ? lines.slice(0, initialLineLimit) : lines;
  const hiddenLineCount = Math.max(0, lines.length - visibleLines.length);

  useEffect(() => {
    setIsExpanded(false);
  }, [content]);

  return (
    <div className="markdown-content">
      {visibleLines.map((line, index) => {
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
      {hiddenLineCount > 0 ? (
        <button
          className="show-more-button"
          onClick={() => setIsExpanded(true)}
          type="button"
        >
          Show {hiddenLineCount} more lines
        </button>
      ) : null}
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
