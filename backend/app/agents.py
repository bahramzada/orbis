import asyncio
import json

from app.openrouter_client import OpenRouterClient
from app.schemas import (
    AgentEdge,
    AgentGraphResponse,
    AgentNode,
    DelegationItem,
    WorkerResult,
    WorkflowRun,
)


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

    async def run(self, task: str) -> WorkflowRun:
        plan = await self._create_plan(task)
        worker_results = await asyncio.gather(
            *(self._run_worker(task, item) for item in plan)
        )
        final_answer = await self._synthesize(task, worker_results)

        return WorkflowRun(
            task=task,
            model=self._client.model,
            plan=plan,
            worker_results=list(worker_results),
            final_answer=final_answer,
        )

    async def _create_plan(self, task: str) -> list[DelegationItem]:
        prompt = (
            "You are the supervisor in a five-agent AI system. "
            "Create exactly four delegation items, one for each worker id: "
            "researcher, strategist, builder, reviewer. "
            "Return strict JSON as an array. Each item must include "
            "worker_id, objective, and expected_output."
        )
        content = await self._client.chat(
            [
                {"role": "system", "content": prompt},
                {"role": "user", "content": task},
            ],
            temperature=0.2,
            max_tokens=900,
        )
        parsed = self._parse_json_array(content)
        items = [DelegationItem.model_validate(item) for item in parsed]
        return self._normalize_plan(items)

    async def _run_worker(self, task: str, item: DelegationItem) -> WorkerResult:
        worker = self._registry.worker_by_id(item.worker_id)
        content = await self._client.chat(
            [
                {
                    "role": "system",
                    "content": (
                        f"You are {worker.name}, the {worker.role} worker. "
                        f"Goal: {worker.goal} "
                        "Respond with concise, practical output for the supervisor."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Main task: {task}\n"
                        f"Your objective: {item.objective}\n"
                        f"Expected output: {item.expected_output}"
                    ),
                },
            ],
            temperature=0.35,
            max_tokens=1200,
        )
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
                    "content": (
                        "You are the supervisor. Combine worker results into a "
                        "clear final answer with decisions, risks, and next steps."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Task:\n{task}\n\nWorker results:\n{worker_payload}",
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
