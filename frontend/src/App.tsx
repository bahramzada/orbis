import { useEffect, useMemo, useState } from "react";
import {
  Activity,
  AlertTriangle,
  Building2,
  BrainCircuit,
  CheckCircle2,
  Loader2,
  Network,
  Play,
  Users
} from "lucide-react";

import { fallbackGraph, fetchAgents, runWorkflowStream } from "./api";
import type { AgentGraph, AgentNode, WorkflowLog, WorkflowRun } from "./types";

type ViewMode = "visual" | "office";

const starterTask =
  "Design a customer support automation flow for a small SaaS team.";

function App() {
  const [graph, setGraph] = useState<AgentGraph>(fallbackGraph);
  const [mode, setMode] = useState<ViewMode>("visual");
  const [task, setTask] = useState(starterTask);
  const [run, setRun] = useState<WorkflowRun | null>(null);
  const [logs, setLogs] = useState<WorkflowLog[]>([]);
  const [error, setError] = useState("");
  const [isRunning, setIsRunning] = useState(false);

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

  async function handleRun() {
    setError("");
    setRun(null);
    setLogs([]);
    setIsRunning(true);
    try {
      const result = await runWorkflowStream(task, (log) => {
        setLogs((currentLogs) => [...currentLogs, log]);
      });
      setRun(result);
      setLogs(result.logs);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Workflow failed.");
    } finally {
      setIsRunning(false);
    }
  }

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
            <textarea value={task} onChange={(event) => setTask(event.target.value)} />
          </label>

          <button
            className="run-button"
            disabled={isRunning || task.trim().length < 3}
            onClick={handleRun}
            type="button"
          >
            {isRunning ? <Loader2 className="spin" size={18} /> : <Play size={18} />}
            Run
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
  return (
    <div className="visual-canvas">
      {graph.edges.map((edge) => {
        const source = graph.agents.find((agent) => agent.id === edge.source);
        const target = graph.agents.find((agent) => agent.id === edge.target);
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

      {graph.agents.map((agent) => (
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
        <CheckCircle2 size={18} />
        <span>{isRunning ? "Starting" : "Ready"}</span>
      </div>
    );
  }

  return (
    <div className="activity-log">
      <div className="activity-heading">
        <strong>Agent Logs</strong>
        <span>{isRunning ? "Running" : "Done"}</span>
      </div>
      {logs
        .slice()
        .reverse()
        .map((log) => (
          <div className={`log-row ${log.status}`} key={`${log.created_at}-${log.agent_id}`}>
            <LogStatusIcon status={log.status} />
            <div>
              <div className="log-meta">
                <strong>{log.agent_name}</strong>
                <time>{formatLogTime(log.created_at)}</time>
              </div>
              <span>{log.message}</span>
            </div>
          </div>
        ))}
    </div>
  );
}

function LogStatusIcon({ status }: { status: WorkflowLog["status"] }) {
  if (status === "completed") {
    return <CheckCircle2 size={17} />;
  }
  if (status === "failed") {
    return <AlertTriangle size={17} />;
  }
  return <Loader2 className="spin" size={17} />;
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
      <h3>Plan</h3>
      {run.plan.map((item) => (
        <div className="result-row" key={item.worker_id}>
          <strong>{item.worker_id}</strong>
          <span>{item.objective}</span>
        </div>
      ))}
      <h3>Worker Outputs</h3>
      {run.worker_results.map((result) => (
        <details className="worker-output" key={result.worker_id}>
          <summary>{result.worker_name}</summary>
          <p>{result.output}</p>
        </details>
      ))}
      <h3>Final</h3>
      <p>{run.final_answer}</p>
    </div>
  );
}

export default App;
