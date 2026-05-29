import asyncio
import json
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from uuid import uuid4

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
    DelegationItem,
    WorkflowLog,
    WorkflowLogStatus,
    WorkerResult,
    WorkflowRun,
)

LogCallback = Callable[[WorkflowLog], Awaitable[None]]


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
    def __init__(self, client: OpenRouterClient, registry: AgentRegistry) -> None:
        self._client = client
        self._registry = registry

    async def run(
        self,
        task: str,
        log_callback: LogCallback | None = None,
    ) -> WorkflowRun:
        run_id = str(uuid4())
        logs: list[WorkflowLog] = []

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

        await emit(SUPERVISOR, "running", "Creating delegation plan.")
        plan = await self._create_plan(task)
        await emit(SUPERVISOR, "completed", f"Delegated work to {len(plan)} agents.")

        worker_results = await asyncio.gather(
            *(self._run_worker(task, item, emit) for item in plan)
        )
        await emit(SUPERVISOR, "running", "Synthesizing worker outputs.")
        final_answer = await self._synthesize(task, worker_results)
        await emit(SUPERVISOR, "completed", "Final answer is ready.")

        return WorkflowRun(
            run_id=run_id,
            task=task,
            model=self._client.model,
            logs=logs,
            plan=plan,
            worker_results=list(worker_results),
            final_answer=final_answer,
        )

    async def _create_plan(self, task: str) -> list[DelegationItem]:
        content = await self._client.chat(
            [
                {"role": "system", "content": build_supervisor_plan_system_prompt()},
                {"role": "user", "content": task},
            ],
            temperature=0.2,
            max_tokens=900,
        )
        parsed = self._parse_json_array(content)
        items = [DelegationItem.model_validate(item) for item in parsed]
        return self._normalize_plan(items)

    async def _run_worker(
        self,
        task: str,
        item: DelegationItem,
        emit: Callable[[AgentNode, WorkflowLogStatus, str], Awaitable[None]],
    ) -> WorkerResult:
        worker = self._registry.worker_by_id(item.worker_id)
        await emit(worker, "running", item.objective)
        content = await self._client.chat(
            [
                {
                    "role": "system",
                    "content": build_worker_system_prompt(
                        worker_id=worker.id,
                        worker_name=worker.name,
                        worker_role=worker.role,
                        worker_goal=worker.goal,
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
            temperature=0.35,
            max_tokens=1200,
        )
        await emit(worker, "completed", "Output returned to supervisor.")
        return WorkerResult(
            worker_id=worker.id,
            worker_name=worker.name,
            objective=item.objective,
            output=content,
        )

    async def _synthesize(
        self,
        task: str,
        worker_results: list[WorkerResult],
    ) -> str:
        worker_payload = "\n\n".join(
            f"{result.worker_name} ({result.objective}):\n{result.output}"
            for result in worker_results
        )
        return await self._client.chat(
            [
                {
                    "role": "system",
                    "content": build_synthesis_system_prompt(),
                },
                {
                    "role": "user",
                    "content": build_synthesis_user_prompt(
                        task=task,
                        worker_payload=worker_payload,
                    ),
                },
            ],
            temperature=0.25,
            max_tokens=1600,
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
    def _normalize_plan(items: list[DelegationItem]) -> list[DelegationItem]:
        by_worker = {item.worker_id: item for item in items}
        normalized: list[DelegationItem] = []

        for worker in WORKERS:
            item = by_worker.get(worker.id)
            if item is None:
                item = DelegationItem(
                    worker_id=worker.id,
                    objective=f"Handle the {worker.role.lower()} angle.",
                    expected_output="Concise findings for supervisor synthesis.",
                )
            normalized.append(item)

        return normalized
