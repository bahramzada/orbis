import asyncio
from typing import cast

from app.agents import AgentOrchestrator, AgentRegistry
from app.openrouter_client import OpenRouterClient
from app.schemas import AgentProfile, DelegationItem, MemoryItem, ToolCall


class CapabilityFakeClient:
    model = "test/model"

    async def chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.3,
        max_tokens: int = 1200,
        model: str | None = None,
        timeout_seconds: float | None = None,
        step: str = "chat",
    ) -> str:
        if step == "synthesis":
            return "## Yekun Qərar\nFinal with memory context."
        return f"Worker output from {step}."


def test_run_accepts_plan_profiles_memory_and_tool_calls() -> None:
    asyncio.run(_run_capability_test())


async def _run_capability_test() -> None:
    tool_calls: list[ToolCall] = []
    client = cast(OpenRouterClient, CapabilityFakeClient())
    orchestrator = AgentOrchestrator(client, AgentRegistry())
    plan = [
        DelegationItem(
            worker_id="researcher",
            objective="Research task.",
            expected_output="Research notes.",
        ),
        DelegationItem(
            worker_id="builder",
            objective="Build task.",
            expected_output="Build notes.",
        ),
    ]
    profiles = [
        AgentProfile(
            id="researcher",
            name="Researcher",
            role="Discovery",
            goal="Find grounded context.",
            enabled=True,
        ),
        AgentProfile(
            id="builder",
            name="Builder",
            role="Execution",
            goal="Create deliverables.",
            enabled=False,
        ),
    ]
    memories = [
        MemoryItem(
            id="memory-1",
            title="Brand voice",
            category="brand",
            content="Use concise Azerbaijani.",
            enabled=True,
        )
    ]

    async def collect_tool(tool_call: ToolCall) -> None:
        tool_calls.append(tool_call)

    result = await orchestrator.run(
        "Yeni məhsul planı hazırla.",
        tool_callback=collect_tool,
        plan_override=plan,
        agent_profiles=profiles,
        memory_items=memories,
        output_format="roadmap",
    )

    assert [item.worker_id for item in result.plan] == ["researcher"]
    assert len(result.worker_results) == 1
    assert result.tool_calls == tool_calls
    assert result.tool_calls[0].tool_name == "memory_search"
    assert result.output_format == "roadmap"
