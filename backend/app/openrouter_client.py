from typing import Any

import httpx

from app.config import Settings


class OpenRouterClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = httpx.AsyncClient(
            base_url=str(settings.openrouter_base_url).rstrip("/"),
            timeout=settings.request_timeout_seconds,
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
    ) -> str:
        if not self.is_configured:
            raise RuntimeError("OPENROUTER_API_KEY is not configured.")

        response = await self._client.post(
            "/chat/completions",
            headers=self._headers(),
            json={
                "model": self.model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
        )
        response.raise_for_status()
        payload = response.json()
        return self._extract_content(payload)

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
