import { useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  Building2,
  BrainCircuit,
  CheckCircle2,
  LayoutDashboard,
  Loader2,
  LogOut,
  Network,
  Play,
  ShieldCheck,
  XCircle
} from "lucide-react";

import {
  compareEvaluations,
  createMemory,
  fallbackGraph,
  fetchAdminUsers,
  fetchAgentProfiles,
  fetchAgents,
  fetchCurrentAuth,
  fetchMemories,
  fetchTemplates,
  loginUser,
  logoutUser,
  previewPlan,
  registerUser,
  rerunSynthesis,
  rerunWorker,
  runWorkflowStream,
  saveAgentProfiles,
  updateAdminUser,
  updateSystemSettings
} from "./api";
import { ActivityLog } from "./components/ActivityLog";
import { AdminPage } from "./components/AdminPage";
import { AuthPanel } from "./components/AuthPanel";
import { CapabilityControls } from "./components/CapabilityControls";
import { OfficeGraph, VisualGraph } from "./components/GraphViews";
import { RunSummary } from "./components/RunSummary";
import { starterTask } from "./constants";
import type {
  AgentGraph,
  AgentProfile,
  AdminUser,
  AuthUser,
  DelegationItem,
  EvaluationResult,
  MemoryItem,
  OutputFormat,
  SystemSettings,
  ToolCall,
  UserRole,
  WorkflowLog,
  WorkflowRun,
  WorkflowTemplate
} from "./types";
import type { MemoryDraft, RunState, ViewMode } from "./uiTypes";

type AppRoute = "dashboard" | "admin";
type AuthAction = "idle" | "login" | "register" | "logout";

const initialMemoryDraft: MemoryDraft = {
  title: "",
  category: "company context",
  content: ""
};

function App() {
  const [graph, setGraph] = useState<AgentGraph>(fallbackGraph);
  const [mode, setMode] = useState<ViewMode>("visual");
  const [route, setRoute] = useState<AppRoute>(() => routeFromPath());
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
  const [memoryDraft, setMemoryDraft] = useState<MemoryDraft>(initialMemoryDraft);
  const [planState, setPlanState] = useState<RunState>("idle");
  const [profileSaveState, setProfileSaveState] = useState<RunState>("idle");
  const [evaluations, setEvaluations] = useState<EvaluationResult[]>([]);
  const [authUser, setAuthUser] = useState<AuthUser | null>(null);
  const [authReady, setAuthReady] = useState(false);
  const [authMode, setAuthMode] = useState<"login" | "register">("login");
  const [authEmail, setAuthEmail] = useState("");
  const [authPassword, setAuthPassword] = useState("");
  const [authDisplayName, setAuthDisplayName] = useState("");
  const [authError, setAuthError] = useState("");
  const [authAction, setAuthAction] = useState<AuthAction>("idle");
  const [systemSettings, setSystemSettings] = useState<SystemSettings | null>(null);
  const [adminUsers, setAdminUsers] = useState<AdminUser[]>([]);
  const abortControllerRef = useRef<AbortController | null>(null);
  const isRunning = runState === "running";
  const canUseProtectedApi = Boolean(authUser);
  const isAdmin = authUser?.role === "admin";

  const supervisor = useMemo(
    () => graph.agents.find((agent) => agent.kind === "supervisor"),
    [graph.agents]
  );
  const workers = useMemo(
    () => graph.agents.filter((agent) => agent.kind === "worker"),
    [graph.agents]
  );

  useEffect(() => {
    const handlePopState = () => setRoute(routeFromPath());
    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, []);

  useEffect(() => {
    if (!authReady || !canUseProtectedApi) {
      setGraph(fallbackGraph);
      return;
    }
    fetchAgents()
      .then(setGraph)
      .catch(() => setGraph(fallbackGraph));
  }, [authReady, canUseProtectedApi]);

  useEffect(() => {
    fetchCurrentAuth()
      .then((auth) => {
        setAuthUser(auth.user);
        setSystemSettings(auth.system);
      })
      .catch(() => {
        setAuthUser(null);
      })
      .finally(() => setAuthReady(true));
  }, []);

  useEffect(() => {
    if (!authReady || !canUseProtectedApi) {
      return;
    }
    fetchAgentProfiles().then(setProfiles).catch(() => setProfiles([]));
    fetchTemplates().then(setTemplates).catch(() => setTemplates([]));
    fetchMemories().then(setMemories).catch(() => setMemories([]));
  }, [authReady, canUseProtectedApi]);

  useEffect(() => {
    if (!authReady) {
      return;
    }
    if (authUser?.role !== "admin") {
      setAdminUsers([]);
      if (authUser && route === "admin") {
        navigateTo("dashboard", setRoute);
      }
      return;
    }
    fetchAdminUsers().then(setAdminUsers).catch(() => setAdminUsers([]));
  }, [authReady, authUser, route]);

  useEffect(() => {
    if (runState !== "success") {
      return undefined;
    }

    const timeout = window.setTimeout(() => setRunState("idle"), 2200);
    return () => window.clearTimeout(timeout);
  }, [runState]);

  async function handleLogin() {
    if (authAction !== "idle") {
      return;
    }
    setAuthError("");
    setAuthAction("login");
    try {
      const auth = await loginUser({
        email: authEmail.trim(),
        password: authPassword
      });
      setAuthUser(auth.user);
      setSystemSettings(auth.system);
      setAuthPassword("");
      navigateTo("dashboard", setRoute);
    } catch (caught) {
      setAuthError(caught instanceof Error ? caught.message : "Login failed.");
    } finally {
      setAuthAction("idle");
    }
  }

  async function handleRegister() {
    if (authAction !== "idle") {
      return;
    }
    setAuthError("");
    setAuthAction("register");
    try {
      const auth = await registerUser({
        email: authEmail.trim(),
        password: authPassword,
        display_name: authDisplayName.trim()
      });
      setAuthUser(auth.user);
      setSystemSettings(auth.system);
      setAuthPassword("");
      navigateTo("dashboard", setRoute);
    } catch (caught) {
      setAuthError(caught instanceof Error ? caught.message : "Registration failed.");
    } finally {
      setAuthAction("idle");
    }
  }

  function clearAuthenticatedState() {
    setAuthUser(null);
    setProfiles([]);
    setMemories([]);
    setSelectedMemoryIds([]);
    setAdminUsers([]);
    setRun(null);
    setLogs([]);
    setToolCalls([]);
    setEvaluations([]);
  }

  function handleLogout() {
    if (authAction !== "idle") {
      return;
    }
    setAuthAction("logout");
    setAuthError("");
    const logoutRequest = logoutUser({ keepalive: true });
    clearAuthenticatedState();
    setAuthAction("idle");
    navigateTo("dashboard", setRoute);
    void logoutRequest.then((confirmed) => {
      if (!confirmed) {
        setAuthError("Signed out locally. Server logout did not confirm.");
      }
    });
  }

  async function handleRefreshAdmin() {
    try {
      setAdminUsers(await fetchAdminUsers());
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Admin users could not load.");
    }
  }

  async function handleSystemSettingChange(
    field: keyof SystemSettings,
    value: boolean
  ) {
    try {
      const updated = await updateSystemSettings({ [field]: value });
      setSystemSettings(updated);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "System setting failed.");
    }
  }

  async function handleUserRoleChange(userId: string, role: UserRole) {
    try {
      const updated = await updateAdminUser(userId, { role });
      setAdminUsers((currentUsers) =>
        currentUsers.map((user) => (user.id === userId ? updated : user))
      );
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Role update failed.");
    }
  }

  async function handleUserActiveChange(userId: string, isActive: boolean) {
    const current = adminUsers.find((user) => user.id === userId);
    if (!current) {
      return;
    }
    try {
      const updated = await updateAdminUser(userId, {
        role: current.role,
        is_active: isActive
      });
      setAdminUsers((currentUsers) =>
        currentUsers.map((user) => (user.id === userId ? updated : user))
      );
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "User update failed.");
    }
  }

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
      setMemoryDraft(initialMemoryDraft);
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
    if (!canUseProtectedApi) {
      setError("Login is required to run workflows.");
      return;
    }
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
        (log) => setLogs((currentLogs) => [...currentLogs, log]),
        controller.signal,
        {
          memory_ids: selectedMemoryIds,
          agent_profiles: profiles,
          plan: planDraft,
          output_format: outputFormat,
          enable_review_phase: enableReviewPhase
        },
        (toolCall) => setToolCalls((currentToolCalls) => [...currentToolCalls, toolCall])
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

  const runButton = getRunButtonContent(runState);

  if (!authReady) {
    return (
      <main className="auth-screen">
        <section className="auth-card">
          <p className="eyebrow">Orbis</p>
          <h1>Agent Control Room</h1>
          <div className="empty-state">
            <Loader2 className="spin" size={18} />
            Loading session
          </div>
        </section>
      </main>
    );
  }

  if (!authUser) {
    return (
      <main className="auth-screen">
        <section className="auth-card">
          <div>
            <p className="eyebrow">Orbis</p>
            <h1>Agent Control Room</h1>
            <p className="auth-copy">Login or create a guest account to continue.</p>
          </div>
          <AuthPanel
            authAction={authAction}
            authError={authError}
            authMode={authMode}
            displayName={authDisplayName}
            email={authEmail}
            password={authPassword}
            systemSettings={systemSettings}
            onAuthModeChange={setAuthMode}
            onDisplayNameChange={setAuthDisplayName}
            onEmailChange={setAuthEmail}
            onLogin={handleLogin}
            onPasswordChange={setAuthPassword}
            onRegister={handleRegister}
          />
        </section>
      </main>
    );
  }

  return (
    <main className={`app-shell ${route === "admin" ? "admin-shell" : ""}`}>
      <section className="topbar">
        <div>
          <p className="eyebrow">Orbis</p>
          <h1>{route === "admin" ? "Admin Console" : "Agent Control Room"}</h1>
        </div>
        <div className="topbar-actions">
          {route === "dashboard" ? (
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
          ) : null}
          <nav className="toolbar nav-toolbar" aria-label="Main navigation">
            <button
              className={route === "dashboard" ? "active" : ""}
              onClick={() => navigateTo("dashboard", setRoute)}
              type="button"
            >
              <LayoutDashboard size={18} />
              Control
            </button>
            {isAdmin ? (
              <button
                className={route === "admin" ? "active" : ""}
                onClick={() => navigateTo("admin", setRoute)}
                type="button"
              >
                <ShieldCheck size={18} />
                Admin
              </button>
            ) : null}
          </nav>
          <button
            className={`session-button ${authAction === "logout" ? "loading" : ""}`}
            disabled={authAction === "logout"}
            onClick={handleLogout}
            type="button"
          >
            <span>
              {authAction === "logout" ? "Signing out" : authUser.display_name || authUser.email}
              <small>{authAction === "logout" ? "ending session" : authUser.role}</small>
            </span>
            {authAction === "logout" ? (
              <Loader2 className="spin" size={17} />
            ) : (
              <LogOut size={17} />
            )}
          </button>
        </div>
      </section>

      {route === "admin" ? (
        <AdminPage
          adminUsers={adminUsers}
          authUser={authUser}
          error={error}
          systemSettings={systemSettings}
          onRefreshAdmin={handleRefreshAdmin}
          onSystemSettingChange={handleSystemSettingChange}
          onUserActiveChange={handleUserActiveChange}
          onUserRoleChange={handleUserRoleChange}
        />
      ) : (
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
                <span>
                  {isRunning ? "Workflow active" : run ? "Last run ready" : "No run yet"}
                </span>
              </span>
            </label>

            <div className="run-actions">
              <button
                className={`run-button ${runState}`}
                disabled={isRunning || task.trim().length < 3 || !canUseProtectedApi}
                onClick={handleRun}
                type="button"
              >
                {runButton.icon}
                {runButton.label}
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
      )}
    </main>
  );
}

function getRunButtonContent(runState: RunState) {
  if (runState === "running") {
    return { icon: <Loader2 className="spin" size={18} />, label: "Running" };
  }
  if (runState === "success") {
    return { icon: <CheckCircle2 size={18} />, label: "Completed" };
  }
  if (runState === "error") {
    return { icon: <AlertTriangle size={18} />, label: "Retry" };
  }
  return { icon: <Play size={18} />, label: "Run" };
}

function routeFromPath(): AppRoute {
  return window.location.pathname.startsWith("/admin") ? "admin" : "dashboard";
}

function navigateTo(route: AppRoute, setRoute: (route: AppRoute) => void) {
  const path = route === "admin" ? "/admin" : "/";
  if (window.location.pathname !== path) {
    window.history.pushState({}, "", path);
  }
  setRoute(route);
}

export default App;
