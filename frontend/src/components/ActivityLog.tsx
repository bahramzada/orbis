import { useMemo, useState } from "react";
import { Activity, AlertTriangle, CheckCircle2, Loader2 } from "lucide-react";

import { logPreviewLimit } from "../constants";
import type { WorkflowLog } from "../types";

export function ActivityLog({
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
