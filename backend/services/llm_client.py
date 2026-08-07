"""The single seam between this application and an LLM provider.

Phase 1 targets a local Ollama server. Every agent goes through `chat_json()`,
so swapping to a hosted provider means editing this file and two settings —
nothing else in the codebase imports an SDK.

Nothing here is allowed to decide a triage priority. Agents use it to extract
structure and write prose; `services/triage_engine.py` owns the decisions.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from config import settings

logger = logging.getLogger(__name__)


class LLMError(RuntimeError):
    """The provider was unreachable, or returned something unusable."""


class LLMClient:
    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float | None = None,
    ) -> None:
        self.base_url = (base_url or settings.OLLAMA_BASE_URL).rstrip("/")
        self.model = model or settings.OLLAMA_MODEL
        self.timeout = timeout or settings.LLM_TIMEOUT_SECONDS

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type((httpx.HTTPError, LLMError)),
        reraise=True,
    )
    async def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.post(f"{self.base_url}{path}", json=payload)
            except httpx.HTTPError as exc:
                raise LLMError(
                    f"Could not reach Ollama at {self.base_url}. Is `ollama serve` "
                    f"running and `{self.model}` pulled? ({exc})"
                ) from exc

            if response.status_code >= 400:
                raise LLMError(
                    f"Ollama returned {response.status_code}: {response.text[:400]}"
                )
            return response.json()

    async def chat_json(
        self,
        system: str,
        user: str,
        schema: dict[str, Any],
        *,
        temperature: float = 0.0,
    ) -> dict[str, Any]:
        """Ask for a response constrained to `schema` and return it parsed.

        Ollama's `format` field takes a JSON schema and constrains decoding, so
        the reply is valid JSON by construction. We still parse defensively —
        a malformed body should surface as LLMError, not as a stack trace deep
        inside an agent.
        """
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "format": schema,
            "stream": False,
            "options": {"temperature": temperature},
        }

        data = await self._post("/api/chat", payload)
        content = (data.get("message") or {}).get("content", "")

        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            raise LLMError(
                f"Model {self.model} returned non-JSON despite a schema: {content[:400]}"
            ) from exc

        if not isinstance(parsed, dict):
            raise LLMError(f"Expected a JSON object, got {type(parsed).__name__}")
        return parsed

    async def chat_text(self, system: str, user: str, *, temperature: float = 0.2) -> str:
        """Free-text completion, for prose that has no structure worth pinning."""
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
            "options": {"temperature": temperature},
        }
        data = await self._post("/api/chat", payload)
        return (data.get("message") or {}).get("content", "").strip()

    async def health(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.base_url}/api/tags")
                return response.status_code == 200
        except httpx.HTTPError:
            return False


llm = LLMClient()
