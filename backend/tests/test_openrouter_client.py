import asyncio

import httpx

from app.config import Settings
from app.openrouter_client import OpenRouterClient


def test_openrouter_client_retries_transient_errors() -> None:
    asyncio.run(_run_retry_test())


async def _run_retry_test() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(500, json={"error": "temporary"})
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "ok"}}]},
        )

    client = OpenRouterClient(
        Settings(
            OPENROUTER_API_KEY="test-key",  # pragma: allowlist secret
            OPENROUTER_RETRY_ATTEMPTS=2,
            OPENROUTER_RETRY_BASE_SECONDS=0,
        ),
        transport=httpx.MockTransport(handler),
    )

    try:
        result = await client.chat(
            [{"role": "user", "content": "hello"}],
            step="test",
        )
    finally:
        await client.close()

    assert result == "ok"
    assert calls == 2


def test_openrouter_client_uses_ttl_cache_when_enabled() -> None:
    asyncio.run(_run_cache_test())


async def _run_cache_test() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "cached"}}]},
        )

    client = OpenRouterClient(
        Settings(
            OPENROUTER_API_KEY="test-key",  # pragma: allowlist secret
            WORKFLOW_CACHE_TTL_SECONDS=60,
        ),
        transport=httpx.MockTransport(handler),
    )

    try:
        first = await client.chat([{"role": "user", "content": "hello"}])
        second = await client.chat([{"role": "user", "content": "hello"}])
    finally:
        await client.close()

    assert first == "cached"
    assert second == "cached"
    assert calls == 1
