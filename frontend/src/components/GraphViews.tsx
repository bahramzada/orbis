import { Activity, Users } from "lucide-react";
import { useCallback, useLayoutEffect, useMemo, useRef, useState } from "react";

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
  const floorRef = useRef<HTMLDivElement | null>(null);
  const stationRefs = useRef<Map<string, HTMLElement>>(new Map());
  const [connectorLayout, setConnectorLayout] = useState<OfficeConnectorLayout>({
    connectors: [],
    height: 0,
    width: 0
  });
  const orderedWorkers = useMemo(
    () =>
      [
        ...workerOrder
          .map((id) => workers.find((worker) => worker.id === id))
          .filter(Boolean),
        ...workers.filter((worker) => !workerOrder.includes(worker.id))
      ] as AgentNode[],
    [workers]
  );
  const workerCount = orderedWorkers.length;
  const setStationRef = useCallback(
    (id: string) => (node: HTMLElement | null) => {
      if (node) {
        stationRefs.current.set(id, node);
      } else {
        stationRefs.current.delete(id);
      }
    },
    []
  );
  const refreshConnectors = useCallback(() => {
    const floor = floorRef.current;
    if (!floor || !supervisor) {
      setConnectorLayout((current) =>
        current.connectors.length === 0 ? current : { connectors: [], height: 0, width: 0 }
      );
      return;
    }

    const source = stationRefs.current.get(supervisor.id);
    if (!source) {
      return;
    }

    const gap = 10;
    const floorRect = floor.getBoundingClientRect();
    const sourceRect = source.getBoundingClientRect();
    const sourceX = sourceRect.left - floorRect.left + sourceRect.width / 2;
    const sourceY = sourceRect.bottom - floorRect.top + gap;
    const connectors = orderedWorkers.flatMap((worker) => {
      const target = stationRefs.current.get(worker.id);
      if (!target) {
        return [];
      }
      const targetRect = target.getBoundingClientRect();
      return [
        {
          id: `${supervisor.id}-${worker.id}`,
          x1: sourceX,
          x2: targetRect.left - floorRect.left + targetRect.width / 2,
          y1: sourceY,
          y2: targetRect.top - floorRect.top - gap
        }
      ];
    });
    const nextLayout = {
      connectors,
      height: floorRect.height,
      width: floorRect.width
    };
    setConnectorLayout((current) =>
      isSameConnectorLayout(current, nextLayout) ? current : nextLayout
    );
  }, [orderedWorkers, supervisor]);

  useLayoutEffect(() => {
    const frame = window.requestAnimationFrame(refreshConnectors);
    const observedNodes = [
      floorRef.current,
      ...Array.from(stationRefs.current.values())
    ].filter(Boolean) as HTMLElement[];
    let observer: ResizeObserver | undefined;

    if (typeof ResizeObserver !== "undefined") {
      observer = new ResizeObserver(refreshConnectors);
      observedNodes.forEach((node) => observer?.observe(node));
    }

    window.addEventListener("resize", refreshConnectors);
    return () => {
      window.cancelAnimationFrame(frame);
      observer?.disconnect();
      window.removeEventListener("resize", refreshConnectors);
    };
  }, [refreshConnectors]);

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

          <div className="office-floor" ref={floorRef}>
            <svg
              aria-hidden="true"
              className="office-links"
              preserveAspectRatio="none"
              viewBox={`0 0 ${connectorLayout.width} ${connectorLayout.height}`}
            >
              {connectorLayout.connectors.map((connector) => (
                <line
                  className="office-link-line"
                  key={connector.id}
                  x1={connector.x1}
                  x2={connector.x2}
                  y1={connector.y1}
                  y2={connector.y2}
                />
              ))}
            </svg>
            <div className="office-prop prop-water" />
            <div className="office-prop prop-files" />
            <div className="office-prop prop-server" />
            {supervisor ? (
              <OfficeAgentStation agent={supervisor} stationRef={setStationRef(supervisor.id)} />
            ) : null}
            {orderedWorkers.map((agent) => (
              <OfficeAgentStation
                agent={agent}
                key={agent.id}
                stationRef={setStationRef(agent.id)}
              />
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

type OfficeConnector = {
  id: string;
  x1: number;
  x2: number;
  y1: number;
  y2: number;
};

type OfficeConnectorLayout = {
  connectors: OfficeConnector[];
  height: number;
  width: number;
};

function isSameConnectorLayout(
  current: OfficeConnectorLayout,
  next: OfficeConnectorLayout
): boolean {
  return (
    current.width === next.width &&
    current.height === next.height &&
    current.connectors.length === next.connectors.length &&
    current.connectors.every((connector, index) => {
      const nextConnector = next.connectors[index];
      return (
        connector.id === nextConnector.id &&
        connector.x1 === nextConnector.x1 &&
        connector.x2 === nextConnector.x2 &&
        connector.y1 === nextConnector.y1 &&
        connector.y2 === nextConnector.y2
      );
    })
  );
}

function OfficeAgentStation({
  agent,
  stationRef
}: {
  agent: AgentNode;
  stationRef?: (node: HTMLElement | null) => void;
}) {
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
      ref={stationRef}
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
