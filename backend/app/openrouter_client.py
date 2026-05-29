import asyncio
import hashlib
import json
from time import monotonic
from typing import Any

import httpx

from app.config import Settings
from app.metrics import metrics, timer


CacheEntry = tuple[float, str]
MAX_CACHE_ITEMS = 256


class OpenRouterClient:
    def __init__(
        self,
        settings: Settings,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._settings = settings
        self._cache: dict[str, CacheEntry] = {}
        self._client = httpx.AsyncClient(
            base_url=str(settings.openrouter_base_url).rstrip("/"),
            timeout=settings.request_timeout_seconds,
            limits=httpx.Limits(
                max_connections=settings.openrouter_max_connections,
                max_keepalive_connections=settings.openrouter_max_keepalive,
            ),
            transport=transport,
        )

    @property
    def model(self) -> str:
        return self._settings.openrouter_model

    @property
    def is_configured(self) -> bool:
        return self._settings.is_openrouter_configured

    async def close(self) -> None:
        await self._client.aclose()

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
        if not self.is_configured:
            raise RuntimeError("OPENROUTER_API_KEY is not configured.")

        selected_model = model or self.model
        cache_key = self._cache_key(messages, temperature, max_tokens, selected_model)
        cached = self._get_cached(cache_key)
        if cached is not None:
            metrics.increment("orbis_llm_cache_hits_total", {"step": step})
            return cached

        attempts = max(1, self._settings.openrouter_retry_attempts)
        request_body = {
            "model": selected_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        for attempt in range(1, attempts + 1):
            request_timer = timer("orbis_llm_step_duration_seconds", {"step": step})
            try:
                request_options: dict[str, Any] = {}
                if timeout_seconds is not None:
                    request_options["timeout"] = timeout_seconds
                response = await self._client.post(
                    "/chat/completions",
                    headers=self._headers(),
                    json=request_body,
                    **request_options,
                )
                response.raise_for_status()
                payload = response.json()
                content = self._extract_content(payload)
                request_timer.stop()
                metrics.increment(
                    "orbis_llm_requests_total",
                    {"step": step, "status": "completed"},
                )
                self._set_cached(cache_key, content)
                return content
            except (httpx.HTTPStatusError, httpx.RequestError) as exc:
                request_timer.stop()
                if not self._should_retry(exc) or attempt == attempts:
                    metrics.increment(
                        "orbis_llm_requests_total",
                        {"step": step, "status": "failed"},
                    )
                    raise
                metrics.increment(
                    "orbis_llm_retries_total",
                    {"step": step, "status": "retry"},
                )
                await asyncio.sleep(self._retry_delay(attempt))
            except Exception:
                request_timer.stop()
                metrics.increment(
                    "orbis_llm_requests_total",
                    {"step": step, "status": "failed"},
                )
                raise

        raise RuntimeError("OpenRouter retry loop ended unexpectedly.")

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._settings.openrouter_api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": self._settings.openrouter_site_url,
            "X-Title": self._settings.openrouter_app_name,
        }

    @staticmethod
    def _extract_content(payload: dict[str, Any]) -> str:
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            raise RuntimeError("OpenRouter response did not include choices.")

        message = choices[0].get("message")
        if not isinstance(message, dict):
            raise RuntimeError("OpenRouter response did not include a message.")

        content = message.get("content")
        if not isinstance(content, str):
            raise RuntimeError("OpenRouter response content was not text.")

        return content.strip()

    def _cache_key(
        self,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int,
        model: str,
    ) -> str:
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest()

    def _get_cached(self, key: str) -> str | None:
        ttl = self._settings.workflow_cache_ttl_seconds
        if ttl <= 0:
            return None

        entry = self._cache.get(key)
        if entry is None:
            return None

        expires_at, value = entry
        if expires_at <= monotonic():
            self._cache.pop(key, None)
            return None
        return value

    def _set_cached(self, key: str, value: str) -> None:
        ttl = self._settings.workflow_cache_ttl_seconds
        if ttl <= 0:
            return

        if len(self._cache) >= MAX_CACHE_ITEMS:
            oldest_key = min(self._cache, key=lambda item: self._cache[item][0])
            self._cache.pop(oldest_key, None)
        self._cache[key] = (monotonic() + ttl, value)

    def _retry_delay(self, attempt: int) -> float:
        return self._settings.openrouter_retry_base_seconds * (2 ** (attempt - 1))

    @staticmethod
    def _should_retry(exc: httpx.HTTPStatusError | httpx.RequestError) -> bool:
        if isinstance(exc, httpx.RequestError):
            return True

        status_code = exc.response.status_code
        return status_code == 429 or 500 <= status_code <= 599
