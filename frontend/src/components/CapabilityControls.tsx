import {
  BookOpen,
  ChevronDown,
  ClipboardCheck,
  Loader2,
  Save,
  SlidersHorizontal,
  Sparkles
} from "lucide-react";

import { outputFormats } from "../constants";
import type {
  AgentProfile,
  DelegationItem,
  MemoryItem,
  OutputFormat,
  WorkflowTemplate
} from "../types";
import type { MemoryDraft, RunState } from "../uiTypes";

type CapabilityControlsProps = {
  enableReviewPhase: boolean;
  memories: MemoryItem[];
  memoryDraft: MemoryDraft;
  outputFormat: OutputFormat;
  planDraft: DelegationItem[] | null;
  planState: RunState;
  profileSaveState: RunState;
  profiles: AgentProfile[];
  selectedMemoryIds: string[];
  templates: WorkflowTemplate[];
  onCreateMemory: () => void;
  onMemoryDraftChange: (value: MemoryDraft) => void;
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
};

export function CapabilityControls({
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
}: CapabilityControlsProps) {
  return (
    <div className="capability-stack">
      <WorkflowTemplatesPanel
        enableReviewPhase={enableReviewPhase}
        outputFormat={outputFormat}
        templates={templates}
        onOutputFormatChange={onOutputFormatChange}
        onTemplateChange={onTemplateChange}
        onToggleReviewPhase={onToggleReviewPhase}
      />
      <AgentStudioPanel
        profileSaveState={profileSaveState}
        profiles={profiles}
        onProfileChange={onProfileChange}
        onSaveProfiles={onSaveProfiles}
      />
      <MemoryLayerPanel
        memories={memories}
        memoryDraft={memoryDraft}
        selectedMemoryIds={selectedMemoryIds}
        onCreateMemory={onCreateMemory}
        onMemoryDraftChange={onMemoryDraftChange}
        onToggleMemory={onToggleMemory}
      />
      <PlanReviewPanel
        planDraft={planDraft}
        planState={planState}
        onPlanChange={onPlanChange}
        onPreviewPlan={onPreviewPlan}
      />
    </div>
  );
}

function WorkflowTemplatesPanel({
  enableReviewPhase,
  outputFormat,
  templates,
  onOutputFormatChange,
  onTemplateChange,
  onToggleReviewPhase
}: Pick<
  CapabilityControlsProps,
  | "enableReviewPhase"
  | "outputFormat"
  | "templates"
  | "onOutputFormatChange"
  | "onTemplateChange"
  | "onToggleReviewPhase"
>) {
  return (
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
          onChange={(event) =>
            onOutputFormatChange(event.currentTarget.value as OutputFormat)
          }
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
  );
}

function AgentStudioPanel({
  profileSaveState,
  profiles,
  onProfileChange,
  onSaveProfiles
}: Pick<
  CapabilityControlsProps,
  "profileSaveState" | "profiles" | "onProfileChange" | "onSaveProfiles"
>) {
  return (
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
          <AgentProfileEditor
            key={profile.id}
            profile={profile}
            onProfileChange={onProfileChange}
          />
        ))}
      </div>
      <button className="secondary-action" onClick={onSaveProfiles} type="button">
        {profileSaveState === "running" ? (
          <Loader2 className="spin" size={16} />
        ) : (
          <Save size={16} />
        )}
        Save Agent Studio
      </button>
    </details>
  );
}

function AgentProfileEditor({
  profile,
  onProfileChange
}: {
  profile: AgentProfile;
  onProfileChange: CapabilityControlsProps["onProfileChange"];
}) {
  return (
    <article className="profile-card">
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
          onChange={(event) => onProfileChange(profile.id, "model", event.currentTarget.value)}
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
  );
}

function MemoryLayerPanel({
  memories,
  memoryDraft,
  selectedMemoryIds,
  onCreateMemory,
  onMemoryDraftChange,
  onToggleMemory
}: Pick<
  CapabilityControlsProps,
  | "memories"
  | "memoryDraft"
  | "selectedMemoryIds"
  | "onCreateMemory"
  | "onMemoryDraftChange"
  | "onToggleMemory"
>) {
  return (
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
  );
}

function PlanReviewPanel({
  planDraft,
  planState,
  onPlanChange,
  onPreviewPlan
}: Pick<
  CapabilityControlsProps,
  "planDraft" | "planState" | "onPlanChange" | "onPreviewPlan"
>) {
  return (
    <details className="capability-panel">
      <summary>
        <span>
          <ClipboardCheck size={16} />
          Human Plan Review
        </span>
        <ChevronDown size={16} />
      </summary>
      <button className="secondary-action" onClick={onPreviewPlan} type="button">
        {planState === "running" ? (
          <Loader2 className="spin" size={16} />
        ) : (
          <ClipboardCheck size={16} />
        )}
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
                  onPlanChange(
                    item.worker_id,
                    "expected_output",
                    event.currentTarget.value
                  )
                }
              />
            </article>
          ))}
        </div>
      ) : (
        <p className="muted-copy">Generate a supervisor plan, edit worker tasks, then run.</p>
      )}
    </details>
  );
}
