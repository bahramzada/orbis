import asyncio
from typing import cast

from app.agents import AgentOrchestrator, AgentRegistry
from app.config import Settings
from app.openrouter_client import OpenRouterClient
from app.schemas import WorkflowLog


class FakeOpenRouterClient:
    model = "test/model"

    def __init__(self) -> None:
        self.calls = 0

    async def chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.3,
        max_tokens: int = 1200,
        timeout_seconds: float | None = None,
        step: str = "chat",
    ) -> str:
        self.calls += 1
        if self.calls == 1:
            return """
            [
              {
                "worker_id": "researcher",
                "objective": "Find audience facts.",
                "expected_output": "Audience notes."
              },
              {
                "worker_id": "strategist",
                "objective": "Shape the offer.",
                "expected_output": "Positioning notes."
              },
              {
                "worker_id": "builder",
                "objective": "Draft names and slogans.",
                "expected_output": "Creative options."
              },
              {
                "worker_id": "reviewer",
                "objective": "Check the result.",
                "expected_output": "Quality notes."
              }
            ]
            """
        if self.calls <= 5:
            return "Worker output."
        return "Final answer."


def test_orchestrator_collects_workflow_logs() -> None:
    asyncio.run(_run_orchestrator_log_test())


async def _run_orchestrator_log_test() -> None:
    logs: list[WorkflowLog] = []
    client = cast(OpenRouterClient, FakeOpenRouterClient())
    orchestrator = AgentOrchestrator(client, AgentRegistry())

    async def collect(log: WorkflowLog) -> None:
        logs.append(log)

    result = await orchestrator.run("Create a coffee shop launch idea.", collect)

    assert result.final_answer == "Final answer."
    assert len(result.worker_results) == 4
    assert result.logs == logs
    assert len(logs) == 12
    assert logs[0].agent_id == "supervisor"
    assert {log.agent_id for log in logs} == {
        "supervisor",
        "researcher",
        "strategist",
        "builder",
        "reviewer",
    }
    assert any(log.status == "running" for log in logs)
    assert any(log.status == "completed" for log in logs)


class PartiallyFailingOpenRouterClient(FakeOpenRouterClient):
    async def chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.3,
        max_tokens: int = 1200,
        timeout_seconds: float | None = None,
        step: str = "chat",
    ) -> str:
        if step == "worker_builder":
            raise RuntimeError("builder exploded")
        return await super().chat(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout_seconds=timeout_seconds,
            step=step,
        )


def test_orchestrator_isolates_worker_failures() -> None:
    asyncio.run(_run_worker_failure_test())


async def _run_worker_failure_test() -> None:
    logs: list[WorkflowLog] = []
    client = cast(OpenRouterClient, PartiallyFailingOpenRouterClient())
    orchestrator = AgentOrchestrator(
        client,
        AgentRegistry(),
        Settings(
            WORKFLOW_MAX_CONCURRENCY=1,
            WORKFLOW_STEP_TIMEOUT_SECONDS=5,
        ),
    )

    async def collect(log: WorkflowLog) -> None:
        logs.append(log)

    result = await orchestrator.run("Create a coffee shop launch idea.", collect)

    assert result.status == "completed"
    assert len(result.worker_results) == 4
    assert any(log.agent_id == "builder" and log.status == "failed" for log in logs)
    assert "builder exploded" in result.worker_results[2].output
