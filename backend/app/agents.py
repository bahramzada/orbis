import asyncio
import json
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from time import perf_counter
from uuid import uuid4

from app.config import Settings, get_settings
from app.metrics import metrics
from app.openrouter_client import OpenRouterClient
from app.prompts import (
    build_supervisor_plan_system_prompt,
    build_synthesis_system_prompt,
    build_synthesis_user_prompt,
    build_worker_system_prompt,
    build_worker_user_prompt,
)
from app.schemas import (
    AgentEdge,
    AgentGraphResponse,
    AgentNode,
    AgentProfile,
    DelegationItem,
    MemoryItem,
    OutputFormat,
    ToolCall,
    ToolCallStatus,
    WorkflowLog,
    WorkflowLogStatus,
    WorkerResult,
    WorkflowRun,
)

LogCallback = Callable[[WorkflowLog], Awaitable[None]]
ToolCallback = Callable[[ToolCall], Awaitable[None]]


SUPERVISOR = AgentNode(
    id="supervisor",
    name="Supervisor",
    kind="supervisor",
    role="Coordinator",
    goal="Break user goals into worker tasks, compare outputs, and deliver final decisions.",
    x=50,
    y=12,
)

WORKERS = [
    AgentNode(
        id="researcher",
        name="Researcher",
        kind="worker",
        role="Discovery",
        goal="Collect context, assumptions, risks, and missing facts.",
        x=18,
        y=48,
    ),
    AgentNode(
        id="strategist",
        name="Strategist",
        kind="worker",
        role="Planning",
        goal="Turn context into an actionable approach and sequencing.",
        x=38,
        y=72,
    ),
    AgentNode(
        id="builder",
        name="Builder",
        kind="worker",
        role="Execution",
        goal="Design concrete implementation steps and integration details.",
        x=62,
        y=72,
    ),
    AgentNode(
        id="reviewer",
        name="Reviewer",
        kind="worker",
        role="Quality",
        goal="Find gaps, edge cases, and verification requirements.",
        x=82,
        y=48,
    ),
]


class AgentRegistry:
    def __init__(self) -> None:
        self._agents = [SUPERVISOR, *WORKERS]

    def graph(self) -> AgentGraphResponse:
        return AgentGraphResponse(
            agents=self._agents,
            edges=[
                AgentEdge(source=SUPERVISOR.id, target=worker.id, label="delegates")
                for worker in WORKERS
            ],
        )

    def worker_by_id(self, worker_id: str) -> AgentNode:
        for worker in WORKERS:
            if worker.id == worker_id:
                return worker
        raise KeyError(f"Unknown worker id: {worker_id}")


class AgentOrchestrator:
    def __init__(
        self,
        client: OpenRouterClient,
        registry: AgentRegistry,
        settings: Settings | None = None,
    ) -> None:
        self._client = client
        self._registry = registry
        self._settings = settings or get_settings()
        self._semaphore = asyncio.Semaphore(
            max(1, self._settings.workflow_max_concurrency)
        )

    async def run(
        self,
        task: str,
        log_callback: LogCallback | None = None,
        tool_callback: ToolCallback | None = None,
        plan_override: list[DelegationItem] | None = None,
        agent_profiles: list[AgentProfile] | None = None,
        memory_items: list[MemoryItem] | None = None,
        output_format: OutputFormat = "markdown",
        enable_review_phase: bool = False,
    ) -> WorkflowRun:
        run_id = str(uuid4())
        logs: list[WorkflowLog] = []
        tool_calls: list[ToolCall] = []
        started_at = perf_counter()
        profile_map = self._profile_map(agent_profiles or [])
        memory_context = self._memory_context(memory_items or [])

        async def emit(
            agent: AgentNode,
            status: WorkflowLogStatus,
            message: str,
        ) -> None:
            log = WorkflowLog(
                run_id=run_id,
                created_at=datetime.now(UTC).isoformat(),
                agent_id=agent.id,
                agent_name=agent.name,
                status=status,
                message=message,
            )
            logs.append(log)
            if log_callback is not None:
                await log_callback(log)

        async def emit_tool(
            tool_name: str,
            status: ToolCallStatus,
            input_text: str,
            output: str,
        ) -> None:
            tool_call = ToolCall(
                id=str(uuid4()),
                run_id=run_id,
                tool_name=tool_name,
                status=status,
                input=input_text,
                output=output,
                created_at=datetime.now(UTC).isoformat(),
            )
            tool_calls.append(tool_call)
            if tool_callback is not None:
                await tool_callback(tool_call)

        status = "completed"
        if self._semaphore.locked():
            await emit(SUPERVISOR, "queued", "Waiting for an available workflow slot.")

        async with self._semaphore:
            try:
                await emit(SUPERVISOR, "running", "Creating delegation plan.")
                if plan_override is None:
                    plan = await self.create_plan(
                        task,
                        agent_profiles=agent_profiles,
                        memory_items=memory_items,
                    )
                else:
                    plan = self._normalize_plan(
                        plan_override,
                        include_missing=False,
                        agent_profiles=agent_profiles or [],
                    )
                await emit(
                    SUPERVISOR,
                    "completed",
                    f"Delegated work to {len(plan)} agents.",
                )
                await self._run_safe_tools(
                    run_id=run_id,
                    task=task,
                    memory_items=memory_items or [],
                    emit=emit,
                    emit_tool=emit_tool,
                )

                worker_results = await asyncio.gather(
                    *(
                        self._run_worker(
                            task,
                            item,
                            emit,
                            profile_map=profile_map,
                            memory_context=memory_context,
                        )
                        for item in plan
                        if item.enabled
                    )
                )
                if enable_review_phase:
                    review_result = await self._run_collaboration_review(
                        task,
                        list(worker_results),
                        emit,
                        profile_map=profile_map,
                        memory_context=memory_context,
                    )
                    worker_results = [*worker_results, review_result]
                await emit(SUPERVISOR, "running", "Synthesizing worker outputs.")
                final_answer = await self._synthesize(
                    task,
                    list(worker_results),
                    output_format=output_format,
                    memory_context=memory_context,
                )
                await emit(SUPERVISOR, "completed", "Final answer is ready.")
                duration_ms = int((perf_counter() - started_at) * 1000)
                estimated_tokens = self._estimate_tokens(task, list(worker_results), final_answer)

                return WorkflowRun(
                    run_id=run_id,
                    task=task,
                    model=self._client.model,
                    status="completed",
                    logs=logs,
                    plan=plan,
                    worker_results=list(worker_results),
                    final_answer=final_answer,
                    tool_calls=tool_calls,
                    output_format=output_format,
                    duration_ms=duration_ms,
                    estimated_tokens=estimated_tokens,
                    estimated_cost_usd=round(estimated_tokens * 0.0000015, 6),
                )
            except asyncio.CancelledError:
                status = "cancelled"
                await emit(SUPERVISOR, "cancelled", "Workflow was cancelled.")
                raise
            except Exception as exc:
                status = "failed"
                await emit(SUPERVISOR, "failed", f"Workflow failed: {_safe_error(exc)}")
                raise
            finally:
                metrics.observe(
                    "orbis_workflow_duration_seconds",
                    perf_counter() - started_at,
                    {"status": status},
                )
                metrics.increment("orbis_workflows_total", {"status": status})

    async def create_plan(
        self,
        task: str,
        *,
        agent_profiles: list[AgentProfile] | None = None,
        memory_items: list[MemoryItem] | None = None,
    ) -> list[DelegationItem]:
        content = await asyncio.wait_for(
            self._client.chat(
                [
                    {
                        "role": "system",
                        "content": build_supervisor_plan_system_prompt(
                            self._memory_context(memory_items or [])
                        ),
                    },
                    {"role": "user", "content": task},
                ],
                temperature=0.2,
                max_tokens=800,
                timeout_seconds=self._settings.workflow_step_timeout_seconds,
                step="plan",
            ),
            timeout=self._settings.workflow_step_timeout_seconds,
        )
        parsed = self._parse_json_array(content)
        items = [DelegationItem.model_validate(item) for item in parsed]
        return self._normalize_plan(
            items,
            include_missing=True,
            agent_profiles=agent_profiles or [],
        )

    async def _run_worker(
        self,
        task: str,
        item: DelegationItem,
        emit: Callable[[AgentNode, WorkflowLogStatus, str], Awaitable[None]],
        *,
        profile_map: dict[str, AgentProfile],
        memory_context: str,
    ) -> WorkerResult:
        worker = self._registry.worker_by_id(item.worker_id)
        profile = profile_map.get(worker.id)
        await emit(worker, "running", item.objective)
        try:
            content = await asyncio.wait_for(
                self._client.chat(
                    [
                        {
                            "role": "system",
                            "content": build_worker_system_prompt(
                                worker_id=worker.id,
                                worker_name=profile.name if profile else worker.name,
                                worker_role=profile.role if profile else worker.role,
                                worker_goal=profile.goal if profile else worker.goal,
                                custom_system_prompt=profile.system_prompt if profile else "",
                                memory_context=memory_context,
                            ),
                        },
                        {
                            "role": "user",
                            "content": build_worker_user_prompt(
                                main_task=task,
                                objective=item.objective,
                                expected_output=item.expected_output,
                            ),
                        },
                    ],
                    temperature=profile.temperature if profile else 0.3,
                    max_tokens=profile.max_tokens if profile else 900,
                    model=profile.model.strip() if profile and profile.model.strip() else None,
                    timeout_seconds=self._settings.workflow_step_timeout_seconds,
                    step=f"worker_{worker.id}",
                ),
                timeout=self._settings.workflow_step_timeout_seconds,
            )
            await emit(worker, "completed", "Output returned to supervisor.")
        except Exception as exc:
            content = (
                f"{worker.name} failed to complete this step. "
                f"Reason: {_safe_error(exc)}"
            )
            await emit(worker, "failed", content)
            metrics.increment("orbis_worker_failures_total", {"worker_id": worker.id})
        return WorkerResult(
            worker_id=worker.id,
            worker_name=profile.name if profile else worker.name,
            objective=item.objective,
            output=content,
        )

    async def _synthesize(
        self,
        task: str,
        worker_results: list[WorkerResult],
        *,
        output_format: OutputFormat = "markdown",
        memory_context: str = "",
    ) -> str:
        worker_payload = "\n\n".join(
            f"{result.worker_name} ({result.objective}):\n{result.output}"
            for result in worker_results
        )
        return await asyncio.wait_for(
            self._client.chat(
                [
                    {
                        "role": "system",
                        "content": build_synthesis_system_prompt(
                            output_format=output_format,
                            memory_context=memory_context,
                        ),
                    },
                    {
                        "role": "user",
                        "content": build_synthesis_user_prompt(
                            task=task,
                            worker_payload=worker_payload,
                        ),
                    },
                ],
                temperature=0.2,
                max_tokens=1200,
                timeout_seconds=self._settings.workflow_step_timeout_seconds,
                step="synthesis",
            ),
            timeout=self._settings.workflow_step_timeout_seconds,
        )

    @staticmethod
    def _parse_json_array(content: str) -> list[dict[str, str]]:
        cleaned = content.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`")
            cleaned = cleaned.removeprefix("json").strip()
        start = cleaned.find("[")
        end = cleaned.rfind("]")
        if start == -1 or end == -1:
            raise ValueError("Supervisor did not return a JSON array.")

        parsed = json.loads(cleaned[start : end + 1])
        if not isinstance(parsed, list):
            raise ValueError("Supervisor plan JSON was not an array.")
        return parsed

    @staticmethod
    def _normalize_plan(
        items: list[DelegationItem],
        *,
        include_missing: bool,
        agent_profiles: list[AgentProfile] | None = None,
    ) -> list[DelegationItem]:
        disabled_ids = {
            profile.id for profile in agent_profiles or [] if not profile.enabled
        }
        by_worker = {item.worker_id: item for item in items}
        normalized: list[DelegationItem] = []

        for worker in WORKERS:
            if worker.id in disabled_ids:
                continue
            item = by_worker.get(worker.id)
            if item is None:
                if not include_missing:
                    continue
                item = DelegationItem(
                    worker_id=worker.id,
                    objective=f"Handle the {worker.role.lower()} angle.",
                    expected_output="Concise findings for supervisor synthesis.",
                )
            normalized.append(item)

        return normalized

    async def rerun_worker(
        self,
        task: str,
        item: DelegationItem,
        *,
        agent_profiles: list[AgentProfile] | None = None,
        memory_items: list[MemoryItem] | None = None,
    ) -> WorkerResult:
        async def noop_emit(
            _agent: AgentNode,
            _status: WorkflowLogStatus,
            _message: str,
        ) -> None:
            return None

        return await self._run_worker(
            task,
            item,
            noop_emit,
            profile_map=self._profile_map(agent_profiles or []),
            memory_context=self._memory_context(memory_items or []),
        )

    async def rerun_synthesis(
        self,
        task: str,
        worker_results: list[WorkerResult],
        *,
        output_format: OutputFormat = "markdown",
        memory_items: list[MemoryItem] | None = None,
    ) -> str:
        return await self._synthesize(
            task,
            worker_results,
            output_format=output_format,
            memory_context=self._memory_context(memory_items or []),
        )

    async def _run_collaboration_review(
        self,
        task: str,
        worker_results: list[WorkerResult],
        emit: Callable[[AgentNode, WorkflowLogStatus, str], Awaitable[None]],
        *,
        profile_map: dict[str, AgentProfile],
        memory_context: str,
    ) -> WorkerResult:
        review_item = DelegationItem(
            worker_id="reviewer",
            objective="Review actual worker outputs for conflicts, gaps, and final synthesis risks.",
            expected_output="Post-worker review notes for the final supervisor synthesis.",
        )
        payload = "\n\n".join(
            f"{result.worker_name}: {result.output}" for result in worker_results
        )
        return await self._run_worker(
            f"{task}\n\nWorker outputs to review:\n{payload}",
            review_item,
            emit,
            profile_map=profile_map,
            memory_context=memory_context,
        )

    async def _run_safe_tools(
        self,
        *,
        run_id: str,
        task: str,
        memory_items: list[MemoryItem],
        emit: Callable[[AgentNode, WorkflowLogStatus, str], Awaitable[None]],
        emit_tool: Callable[[str, ToolCallStatus, str, str], Awaitable[None]],
    ) -> None:
        if memory_items:
            output = f"Loaded {len(memory_items)} selected memory item(s)."
            await emit_tool("memory_search", "completed", task[:300], output)
            await emit(SUPERVISOR, "completed", output)
        else:
            await emit_tool("memory_search", "completed", task[:300], "No memory selected.")

        if any(char.isdigit() for char in task):
            await emit_tool(
                "calculator",
                "completed",
                "Task numeric scan",
                "Numeric values detected; no arithmetic expression was executed.",
            )

    @staticmethod
    def _profile_map(profiles: list[AgentProfile]) -> dict[str, AgentProfile]:
        return {profile.id: profile for profile in profiles}

    @staticmethod
    def _memory_context(memory_items: list[MemoryItem]) -> str:
        enabled = [item for item in memory_items if item.enabled]
        if not enabled:
            return ""
        return "\n".join(
            f"- {item.category}: {item.title}: {item.content[:1000]}" for item in enabled
        )

    @staticmethod
    def _estimate_tokens(
        task: str,
        worker_results: list[WorkerResult],
        final_answer: str,
    ) -> int:
        text = task + final_answer + "".join(result.output for result in worker_results)
        return max(1, len(text) // 4)


def _safe_error(exc: Exception) -> str:
    message = str(exc) or exc.__class__.__name__
    return message.replace("\n", " ")[:240]
