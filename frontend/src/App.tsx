import type { CSSProperties, ReactNode } from "react";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  Activity,
  AlertTriangle,
  Building2,
  BrainCircuit,
  BookOpen,
  CheckCircle2,
  ChevronDown,
  ClipboardCheck,
  Gauge,
  Loader2,
  Network,
  Play,
  RotateCcw,
  Save,
  SlidersHorizontal,
  Sparkles,
  Users,
  XCircle
} from "lucide-react";

import {
  compareEvaluations,
  createMemory,
  fallbackGraph,
  fetchAgentProfiles,
  fetchAgents,
  fetchMemories,
  fetchTemplates,
  previewPlan,
  rerunSynthesis,
  rerunWorker,
  runWorkflowStream,
  saveAgentProfiles
} from "./api";
import type {
  AgentGraph,
  AgentNode,
  AgentProfile,
  DelegationItem,
  EvaluationResult,
  MemoryItem,
  OutputFormat,
  ToolCall,
  WorkflowTemplate,
  WorkflowLog,
  WorkflowRun
} from "./types";

type ViewMode = "visual" | "office";
type RunState = "idle" | "running" | "success" | "error";

const starterTask =
  "Design a customer support automation flow for a small SaaS team.";
const logPreviewLimit = 80;
const markdownInitialLineLimit = 140;
const outputFormats: OutputFormat[] = [
  "markdown",
  "checklist",
  "roadmap",
  "table",
  "json",
  "prd",
  "test_plan"
];

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
  const [toolCalls, setToolCalls] = useState<ToolCall[]>([]);
  const [error, setError] = useState("");
  const [runState, setRunState] = useState<RunState>("idle");
  const [profiles, setProfiles] = useState<AgentProfile[]>([]);
  const [templates, setTemplates] = useState<WorkflowTemplate[]>([]);
  const [memories, setMemories] = useState<MemoryItem[]>([]);
  const [selectedMemoryIds, setSelectedMemoryIds] = useState<string[]>([]);
  const [planDraft, setPlanDraft] = useState<DelegationItem[] | null>(null);
  const [outputFormat, setOutputFormat] = useState<OutputFormat>("markdown");
  const [enableReviewPhase, setEnableReviewPhase] = useState(false);
  const [memoryDraft, setMemoryDraft] = useState({
    title: "",
    category: "company context",
    content: ""
  });
  const [planState, setPlanState] = useState<RunState>("idle");
  const [profileSaveState, setProfileSaveState] = useState<RunState>("idle");
  const [evaluations, setEvaluations] = useState<EvaluationResult[]>([]);
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
    fetchAgentProfiles().then(setProfiles).catch(() => setProfiles([]));
    fetchTemplates().then(setTemplates).catch(() => setTemplates([]));
    fetchMemories().then(setMemories).catch(() => setMemories([]));
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
      setPlanDraft(null);
    }
  }

  function handleProfileChange(
    id: string,
    field: keyof AgentProfile,
    value: string | number | boolean
  ) {
    setProfiles((currentProfiles) =>
      currentProfiles.map((profile) =>
        profile.id === id ? { ...profile, [field]: value } : profile
      )
    );
  }

  async function handleSaveProfiles() {
    setProfileSaveState("running");
    try {
      const saved = await saveAgentProfiles(profiles);
      setProfiles(saved);
      setProfileSaveState("success");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Profiles could not be saved.");
      setProfileSaveState("error");
    }
  }

  async function handleCreateMemory() {
    if (!memoryDraft.title.trim() || !memoryDraft.content.trim()) {
      return;
    }
    try {
      const item = await createMemory({
        title: memoryDraft.title.trim(),
        category: memoryDraft.category.trim() || "general",
        content: memoryDraft.content.trim(),
        enabled: true
      });
      setMemories((currentMemories) => [item, ...currentMemories]);
      setSelectedMemoryIds((currentIds) => [item.id, ...currentIds]);
      setMemoryDraft({ title: "", category: "company context", content: "" });
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Memory could not be saved.");
    }
  }

  function toggleMemory(id: string) {
    setSelectedMemoryIds((currentIds) =>
      currentIds.includes(id)
        ? currentIds.filter((currentId) => currentId !== id)
        : [...currentIds, id]
    );
  }

  function handleTemplateChange(templateId: string) {
    const template = templates.find((item) => item.id === templateId);
    if (!template) {
      return;
    }
    setTask(template.task_prompt);
    setOutputFormat(template.output_format);
    setPlanDraft(null);
  }

  async function handlePreviewPlan() {
    setPlanState("running");
    setError("");
    try {
      const plan = await previewPlan(task, selectedMemoryIds, profiles);
      setPlanDraft(plan);
      setPlanState("success");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Plan could not be created.");
      setPlanState("error");
    }
  }

  function handlePlanChange(
    workerId: string,
    field: keyof DelegationItem,
    value: string | boolean
  ) {
    setPlanDraft((currentPlan) =>
      currentPlan
        ? currentPlan.map((item) =>
            item.worker_id === workerId ? { ...item, [field]: value } : item
          )
        : currentPlan
    );
  }

  async function handleRun() {
    abortControllerRef.current?.abort();
    const controller = new AbortController();
    abortControllerRef.current = controller;
    setError("");
    setRun(null);
    setLogs([]);
    setToolCalls([]);
    setEvaluations([]);
    setRunState("running");
    try {
      const result = await runWorkflowStream(
        task,
        (log) => {
          setLogs((currentLogs) => [...currentLogs, log]);
        },
        controller.signal,
        {
          memory_ids: selectedMemoryIds,
          agent_profiles: profiles,
          plan: planDraft,
          output_format: outputFormat,
          enable_review_phase: enableReviewPhase
        },
        (toolCall) => {
          setToolCalls((currentToolCalls) => [...currentToolCalls, toolCall]);
        }
      );
      setRun(result);
      setLogs(result.logs);
      setToolCalls(result.tool_calls);
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

  async function handleRerunWorker(workerId: string) {
    if (!run) {
      return;
    }
    setError("");
    try {
      const detail = await rerunWorker(run.run_id, workerId, {
        memory_ids: selectedMemoryIds,
        agent_profiles: profiles
      });
      setRun(detail);
      setEvaluations(detail.evaluations);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Worker rerun failed.");
    }
  }

  async function handleRerunSynthesis() {
    if (!run) {
      return;
    }
    setError("");
    try {
      const detail = await rerunSynthesis(run.run_id, outputFormat, selectedMemoryIds);
      setRun(detail);
      setEvaluations(detail.evaluations);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Synthesis rerun failed.");
    }
  }

  async function handleEvaluate() {
    if (!run) {
      return;
    }
    setError("");
    try {
      const scores = await compareEvaluations([run.run_id]);
      setEvaluations(scores);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Evaluation failed.");
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
          <CapabilityControls
            enableReviewPhase={enableReviewPhase}
            memories={memories}
            memoryDraft={memoryDraft}
            outputFormat={outputFormat}
            planDraft={planDraft}
            planState={planState}
            profileSaveState={profileSaveState}
            profiles={profiles}
            selectedMemoryIds={selectedMemoryIds}
            templates={templates}
            onCreateMemory={handleCreateMemory}
            onMemoryDraftChange={setMemoryDraft}
            onPlanChange={handlePlanChange}
            onPreviewPlan={handlePreviewPlan}
            onProfileChange={handleProfileChange}
            onSaveProfiles={handleSaveProfiles}
            onTemplateChange={handleTemplateChange}
            onToggleMemory={toggleMemory}
            onToggleReviewPhase={setEnableReviewPhase}
            onOutputFormatChange={setOutputFormat}
          />
          <ActivityLog logs={run?.logs.length ? run.logs : logs} isRunning={isRunning} />
          <RunSummary
            evaluations={evaluations}
            run={run}
            toolCalls={run?.tool_calls.length ? run.tool_calls : toolCalls}
            onEvaluate={handleEvaluate}
            onRerunSynthesis={handleRerunSynthesis}
            onRerunWorker={handleRerunWorker}
          />
        </aside>
      </section>
    </main>
  );
}

function CapabilityControls({
  enableReviewPhase,
  memories,
  memoryDraft,
  outputFormat,
  planDraft,
  planState,
  profileSaveState,
  profiles,
  selectedMemoryIds,
  templates,
  onCreateMemory,
  onMemoryDraftChange,
  onOutputFormatChange,
  onPlanChange,
  onPreviewPlan,
  onProfileChange,
  onSaveProfiles,
  onTemplateChange,
  onToggleMemory,
  onToggleReviewPhase
}: {
  enableReviewPhase: boolean;
  memories: MemoryItem[];
  memoryDraft: { title: string; category: string; content: string };
  outputFormat: OutputFormat;
  planDraft: DelegationItem[] | null;
  planState: RunState;
  profileSaveState: RunState;
  profiles: AgentProfile[];
  selectedMemoryIds: string[];
  templates: WorkflowTemplate[];
  onCreateMemory: () => void;
  onMemoryDraftChange: (value: { title: string; category: string; content: string }) => void;
  onOutputFormatChange: (value: OutputFormat) => void;
  onPlanChange: (
    workerId: string,
    field: keyof DelegationItem,
    value: string | boolean
  ) => void;
  onPreviewPlan: () => void;
  onProfileChange: (
    id: string,
    field: keyof AgentProfile,
    value: string | number | boolean
  ) => void;
  onSaveProfiles: () => void;
  onTemplateChange: (templateId: string) => void;
  onToggleMemory: (id: string) => void;
  onToggleReviewPhase: (value: boolean) => void;
}) {
  return (
    <div className="capability-stack">
      <details className="capability-panel">
        <summary>
          <span>
            <Sparkles size={16} />
            Workflow Templates
          </span>
          <ChevronDown size={16} />
        </summary>
        <div className="template-grid">
          {templates.map((template) => (
            <button
              key={template.id}
              onClick={() => onTemplateChange(template.id)}
              type="button"
            >
              <strong>{template.name}</strong>
              <small>{template.description}</small>
            </button>
          ))}
        </div>
        <label className="compact-field">
          <span>Final output</span>
          <select
            value={outputFormat}
            onChange={(event) => onOutputFormatChange(event.currentTarget.value as OutputFormat)}
          >
            {outputFormats.map((format) => (
              <option key={format} value={format}>
                {format.replace("_", " ")}
              </option>
            ))}
          </select>
        </label>
        <label className="toggle-row">
          <input
            checked={enableReviewPhase}
            onChange={(event) => onToggleReviewPhase(event.currentTarget.checked)}
            type="checkbox"
          />
          <span>Second-stage reviewer sees worker outputs before final synthesis</span>
        </label>
      </details>

      <details className="capability-panel">
        <summary>
          <span>
            <SlidersHorizontal size={16} />
            Agent Studio
          </span>
          <ChevronDown size={16} />
        </summary>
        <div className="profile-grid">
          {profiles.map((profile) => (
            <article className="profile-card" key={profile.id}>
              <label className="toggle-row">
                <input
                  checked={profile.enabled}
                  onChange={(event) =>
                    onProfileChange(profile.id, "enabled", event.currentTarget.checked)
                  }
                  type="checkbox"
                />
                <strong>{profile.id}</strong>
              </label>
              <input
                aria-label={`${profile.id} name`}
                value={profile.name}
                onChange={(event) => onProfileChange(profile.id, "name", event.currentTarget.value)}
              />
              <input
                aria-label={`${profile.id} role`}
                value={profile.role}
                onChange={(event) => onProfileChange(profile.id, "role", event.currentTarget.value)}
              />
              <textarea
                aria-label={`${profile.id} goal`}
                value={profile.goal}
                onChange={(event) => onProfileChange(profile.id, "goal", event.currentTarget.value)}
              />
              <div className="profile-controls">
                <input
                  aria-label={`${profile.id} model`}
                  placeholder="default model"
                  value={profile.model}
                  onChange={(event) =>
                    onProfileChange(profile.id, "model", event.currentTarget.value)
                  }
                />
                <input
                  aria-label={`${profile.id} temperature`}
                  max="2"
                  min="0"
                  step="0.1"
                  type="number"
                  value={profile.temperature}
                  onChange={(event) =>
                    onProfileChange(profile.id, "temperature", Number(event.currentTarget.value))
                  }
                />
                <input
                  aria-label={`${profile.id} token limit`}
                  max="8000"
                  min="128"
                  step="64"
                  type="number"
                  value={profile.max_tokens}
                  onChange={(event) =>
                    onProfileChange(profile.id, "max_tokens", Number(event.currentTarget.value))
                  }
                />
              </div>
              <textarea
                aria-label={`${profile.id} system prompt`}
                placeholder="Optional extra system prompt"
                value={profile.system_prompt}
                onChange={(event) =>
                  onProfileChange(profile.id, "system_prompt", event.currentTarget.value)
                }
              />
            </article>
          ))}
        </div>
        <button className="secondary-action" onClick={onSaveProfiles} type="button">
          {profileSaveState === "running" ? <Loader2 className="spin" size={16} /> : <Save size={16} />}
          Save Agent Studio
        </button>
      </details>

      <details className="capability-panel">
        <summary>
          <span>
            <BookOpen size={16} />
            Memory Layer
          </span>
          <ChevronDown size={16} />
        </summary>
        <div className="memory-form">
          <input
            placeholder="Memory title"
            value={memoryDraft.title}
            onChange={(event) =>
              onMemoryDraftChange({ ...memoryDraft, title: event.currentTarget.value })
            }
          />
          <input
            placeholder="Category"
            value={memoryDraft.category}
            onChange={(event) =>
              onMemoryDraftChange({ ...memoryDraft, category: event.currentTarget.value })
            }
          />
          <textarea
            placeholder="Company context, brand voice, constraints..."
            value={memoryDraft.content}
            onChange={(event) =>
              onMemoryDraftChange({ ...memoryDraft, content: event.currentTarget.value })
            }
          />
          <button className="secondary-action" onClick={onCreateMemory} type="button">
            <Save size={16} />
            Add Memory
          </button>
        </div>
        <div className="memory-list">
          {memories.length === 0 ? <span>No saved memory yet</span> : null}
          {memories.map((memory) => (
            <label className="memory-row" key={memory.id}>
              <input
                checked={selectedMemoryIds.includes(memory.id)}
                onChange={() => onToggleMemory(memory.id)}
                type="checkbox"
              />
              <span>
                <strong>{memory.title}</strong>
                <small>{memory.category}</small>
              </span>
            </label>
          ))}
        </div>
      </details>

      <details className="capability-panel">
        <summary>
          <span>
            <ClipboardCheck size={16} />
            Human Plan Review
          </span>
          <ChevronDown size={16} />
        </summary>
        <button className="secondary-action" onClick={onPreviewPlan} type="button">
          {planState === "running" ? <Loader2 className="spin" size={16} /> : <ClipboardCheck size={16} />}
          Preview Plan
        </button>
        {planDraft ? (
          <div className="plan-review">
            {planDraft.map((item) => (
              <article className="plan-edit-row" key={item.worker_id}>
                <label className="toggle-row">
                  <input
                    checked={item.enabled}
                    onChange={(event) =>
                      onPlanChange(item.worker_id, "enabled", event.currentTarget.checked)
                    }
                    type="checkbox"
                  />
                  <strong>{item.worker_id}</strong>
                </label>
                <textarea
                  value={item.objective}
                  onChange={(event) =>
                    onPlanChange(item.worker_id, "objective", event.currentTarget.value)
                  }
                />
                <textarea
                  value={item.expected_output}
                  onChange={(event) =>
                    onPlanChange(item.worker_id, "expected_output", event.currentTarget.value)
                  }
                />
              </article>
            ))}
          </div>
        ) : (
          <p className="muted-copy">Generate a supervisor plan, edit worker tasks, then run.</p>
        )}
      </details>
    </div>
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

function RunSummary({
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
      <div className="model-pill">{run.model}</div>
      <div className="inspector-grid" aria-label="Run inspector">
        <span>
          <Gauge size={15} />
          {run.duration_ms ? `${(run.duration_ms / 1000).toFixed(1)}s` : "n/a"}
        </span>
        <span>{run.estimated_tokens || 0} est. tokens</span>
        <span>${run.estimated_cost_usd.toFixed(6)}</span>
        <span>{run.output_format}</span>
      </div>
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
      {evaluations.length > 0 ? (
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
      ) : null}
      {toolCalls.length > 0 ? (
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
      ) : null}
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
