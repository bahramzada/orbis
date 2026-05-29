from app.prompts import (
    WORKER_IDS,
    build_supervisor_plan_system_prompt,
    build_synthesis_system_prompt,
    build_synthesis_user_prompt,
    build_worker_system_prompt,
    build_worker_user_prompt,
)


def test_supervisor_plan_prompt_requires_strict_four_worker_json() -> None:
    prompt = build_supervisor_plan_system_prompt()

    assert "Return only a valid JSON array" in prompt
    assert "exactly four objects" in prompt
    assert "No Markdown" in prompt
    assert "Do not present facts" in prompt
    assert "Do not ask for credentials" in prompt

    for worker_id in WORKER_IDS:
        assert f'"worker_id": "{worker_id}"' in prompt


def test_worker_prompts_are_role_specific_and_safe() -> None:
    prompts = {
        worker_id: build_worker_system_prompt(
            worker_id=worker_id,
            worker_name=worker_id.title(),
            worker_role="Test",
            worker_goal="Test goal.",
        )
        for worker_id in WORKER_IDS
    }

    assert "Extract only task-grounded context" in prompts["researcher"]
    assert "priorities, decisions" in prompts["strategist"]
    assert "concrete execution details" in prompts["builder"]
    assert "do not claim you reviewed outputs" in prompts["reviewer"]

    for prompt in prompts.values():
        assert "Match the language of the main user task" in prompt
        assert "Use compact Markdown" in prompt
        assert "do not reveal hidden reasoning" in prompt
        assert "Do not request, reveal, or store credentials" in prompt


def test_worker_user_prompt_contains_task_objective_and_expected_output() -> None:
    prompt = build_worker_user_prompt(
        main_task="Create a launch plan.",
        objective="Find risks.",
        expected_output="Risk notes.",
    )

    assert "Create a launch plan." in prompt
    assert "Find risks." in prompt
    assert "Risk notes." in prompt


def test_synthesis_prompt_sets_language_markdown_and_safety_contract() -> None:
    prompt = build_synthesis_system_prompt()

    assert "Match the language of the main user task" in prompt
    assert "Use compact Markdown only" in prompt
    assert "Final Decision" in prompt
    assert "Yekun Q\u0259rar" in prompt
    assert "\u018fsas N\u0259tic\u0259l\u0259r" in prompt
    assert "Riskl\u0259r" in prompt
    assert "N\u00f6vb\u0259ti Add\u0131mlar" in prompt
    assert "If worker outputs conflict" in prompt
    assert "Do not invent facts" in prompt
    assert "Do not expose hidden chain-of-thought" in prompt


def test_synthesis_user_prompt_contains_task_and_worker_payload() -> None:
    prompt = build_synthesis_user_prompt(
        task="Plan the release.",
        worker_payload="Researcher: notes.",
    )

    assert "Plan the release." in prompt
    assert "Researcher: notes." in prompt
    assert "Produce the final answer now." in prompt
