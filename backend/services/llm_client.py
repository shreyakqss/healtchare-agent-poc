"""The single seam between this application and an LLM provider.

Targets the OpenAI chat-completions API over plain httpx — no provider SDK is
imported here or anywhere else, so swapping providers stays a one-file change.
Every agent goes through `chat_json()`, `chat_text()` or `stream_text()`.

Nothing here is allowed to decide a triage priority. Agents use it to extract
structure and write prose; `services/triage_engine.py` owns the decisions.

Two things about the current model family are worth knowing before editing:

* **Reasoning models reject `temperature`.** `gpt-5.x` and friends 400 on it,
  while older chat models 400 on `reasoning_effort`. `LLM_SUPPORTS_EFFORT`
  picks which of the two is sent, so a model swap is a settings change rather
  than a code change.
* **Strict structured output is fussier than Ollama's grammar was.** The
  schemas in `schemas/agent_outputs.py` are built for Ollama, which happily
  took Pydantic's numeric bounds; OpenAI's strict mode rejects them. `_strict`
  below sanitises the schema, and `chat_json` falls back to plain JSON mode
  with the schema in the prompt if the API still refuses it.
"""
import json
import logging
from collections.abc import AsyncIterator
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


# Keywords OpenAI's strict schema validator rejects. Pydantic emits several of
# them from ordinary `Field(...)` constraints — `confidence: float = Field(ge=0,
# le=1)` alone produces two — so they are dropped rather than hand-removed from
# the models, which still need them for validation on the way back in.
_UNSUPPORTED = frozenset(
    {
        "minimum",
        "maximum",
        "exclusiveMinimum",
        "exclusiveMaximum",
        "multipleOf",
        "minLength",
        "maxLength",
        "pattern",
        "minItems",
        "maxItems",
        "uniqueItems",
        "format",
        "default",
        "examples",
    }
)


def _strict(node: Any) -> Any:
    """Make a Pydantic JSON schema acceptable to strict structured output.

    Drops the constraint keywords strict mode refuses, and marks every object
    closed. `json_schema()` in `schemas/agent_outputs.py` has already inlined
    `$defs` and forced every property into `required`, which are the other two
    conditions.
    """
    if isinstance(node, dict):
        cleaned = {k: _strict(v) for k, v in node.items() if k not in _UNSUPPORTED}
        if cleaned.get("type") == "object":
            cleaned["additionalProperties"] = False
            cleaned.setdefault("properties", {})
            cleaned["required"] = list(cleaned["properties"])
        return cleaned
    if isinstance(node, list):
        return [_strict(item) for item in node]
    return node


class LLMClient:
    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float | None = None,
        api_key: str | None = None,
    ) -> None:
        self.base_url = (base_url or settings.LLM_BASE_URL).rstrip("/")
        self.model = model or settings.LLM_MODEL
        self.timeout = timeout or settings.LLM_TIMEOUT_SECONDS
        self.api_key = api_key or settings.OPENAI_API_KEY

    # --- plumbing ----------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        if not self.api_key:
            raise LLMError(
                "OPENAI_API_KEY is not set. Add it to backend/.env — every agent "
                "degrades to a documented fallback without it, so the workflow "
                "still runs, but nothing will be generated."
            )
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _tuning(self, temperature: float) -> dict[str, Any]:
        """Whichever of effort/temperature this model actually accepts."""
        if settings.LLM_SUPPORTS_EFFORT:
            return {"reasoning_effort": settings.LLM_EFFORT}
        return {"temperature": temperature}

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type((httpx.HTTPError, LLMError)),
        reraise=True,
    )
    async def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    headers=self._headers(),
                )
            except httpx.HTTPError as exc:
                raise LLMError(
                    f"Could not reach {self.base_url} ({exc})"
                ) from exc

            if response.status_code >= 400:
                raise LLMError(
                    f"OpenAI returned {response.status_code}: {response.text[:500]}"
                )
            return response.json()

    @staticmethod
    def _content(data: dict[str, Any]) -> str:
        choices = data.get("choices") or []
        if not choices:
            raise LLMError("The provider returned no choices.")
        message = choices[0].get("message") or {}
        if message.get("refusal"):
            raise LLMError(f"The provider refused: {message['refusal']}")
        return message.get("content") or ""

    # --- the three calls every agent uses ----------------------------------

    async def chat_json(
        self,
        system: str,
        user: str,
        schema: dict[str, Any],
        *,
        temperature: float = 0.0,
    ) -> dict[str, Any]:
        """Ask for a response constrained to `schema` and return it parsed.

        Tries strict structured output first, which makes the reply valid JSON
        by construction. If the API rejects the schema itself — the sanitiser
        cannot anticipate every keyword — it retries once in plain JSON mode
        with the schema pasted into the prompt, which is weaker but works. Both
        paths parse defensively: a malformed body must surface as `LLMError`,
        not as a stack trace deep inside an agent.
        """
        base = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            **self._tuning(temperature),
        }

        payload = {
            **base,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "agent_output",
                    "strict": True,
                    "schema": _strict(schema),
                },
            },
        }

        try:
            data = await self._post(payload)
        except LLMError as exc:
            if "response_format" not in str(exc) and "schema" not in str(exc):
                raise
            logger.warning(
                "Strict schema was rejected; falling back to JSON mode. %s", exc
            )
            data = await self._post(
                {
                    **base,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {"role": "system", "content": system},
                        {
                            "role": "user",
                            "content": (
                                f"{user}\n\nReply with JSON matching this schema "
                                f"exactly:\n{json.dumps(schema)}"
                            ),
                        },
                    ],
                }
            )

        content = self._content(data)
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
        data = await self._post(
            {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                **self._tuning(temperature),
            }
        )
        return self._content(data).strip()

    async def stream_text(
        self, system: str, user: str, *, temperature: float = 0.2
    ) -> AsyncIterator[str]:
        """`chat_text`, yielded as the model produces it.

        OpenAI answers `stream: true` with server-sent events: `data: {...}`
        per frame and a final `data: [DONE]`. The reply is the concatenation of
        the deltas, so a caller that only wants the whole thing can join them —
        which is why there is no third prose method.

        Deliberately not wrapped in tenacity: by the time a stream breaks the
        patient has already seen half a sentence, and a silent replay would
        duplicate it. A break surfaces as `LLMError` like any other failure and
        the caller decides.
        """
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": True,
            **self._tuning(temperature),
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                async with client.stream(
                    "POST",
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    headers=self._headers(),
                ) as response:
                    if response.status_code >= 400:
                        body = (await response.aread()).decode(errors="replace")
                        raise LLMError(
                            f"OpenAI returned {response.status_code}: {body[:500]}"
                        )
                    async for line in response.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if not data:
                            continue
                        if data == "[DONE]":
                            return
                        try:
                            frame = json.loads(data)
                        except json.JSONDecodeError:
                            # One unreadable frame is not worth failing a reply
                            # the patient is already watching arrive.
                            logger.warning("Skipped an unparseable stream frame")
                            continue
                        for choice in frame.get("choices") or []:
                            chunk = (choice.get("delta") or {}).get("content")
                            if chunk:
                                yield chunk
        except httpx.HTTPError as exc:
            raise LLMError(f"Could not reach {self.base_url} ({exc})") from exc

    async def health(self) -> bool:
        """Is the configured model reachable with the configured key?

        Retrieves the single model rather than listing every one: the list
        endpoint returns hundreds of entries and read-timed-out on a cold
        connection, which made this report a false negative. Asking for the
        one model we actually use is both cheaper and a stronger check — a
        typo in `LLM_MODEL` fails here rather than at the first patient turn.
        """
        if not self.api_key:
            return False
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                response = await client.get(
                    f"{self.base_url}/models/{self.model}", headers=self._headers()
                )
                return response.status_code == 200
        except (httpx.HTTPError, LLMError):
            return False


llm = LLMClient()
