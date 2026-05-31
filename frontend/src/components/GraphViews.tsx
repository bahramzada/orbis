import { Activity, Users } from "lucide-react";

import { officeAgentMeta, visualPositionOverrides, workerOrder } from "../constants";
import type { AgentGraph, AgentNode } from "../types";

export function VisualGraph({ graph }: { graph: AgentGraph }) {
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
      className={`agent-badge ${agent.kind} agent-${agent.id}`}
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

export function OfficeGraph({
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
              <defs>
                <marker
                  id="office-arrow"
                  markerHeight="7"
                  markerWidth="7"
                  orient="auto"
                  refX="6"
                  refY="3.5"
                  viewBox="0 0 7 7"
                >
                  <path d="M0 0 L7 3.5 L0 7 Z" />
                </marker>
              </defs>
              <path d="M50 30 C43 36 34 42 24 44" />
              <path d="M50 30 C57 36 66 42 76 44" />
              <path d="M49 31 C44 46 39 60 36 70" />
              <path d="M51 31 C56 46 61 60 64 70" />
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
                <dt>State</dt>
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
      bubble: agent.role
    } satisfies (typeof officeAgentMeta)[string]);

  return (
    <article
      className={`office-agent station-${meta.slot} ${agent.kind}`}
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
    </article>
  );
}
