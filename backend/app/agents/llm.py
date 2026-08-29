"""Single place that constructs agno models and agents.

Swapping provider = editing `build_model()`. Nothing else imports a provider class.
"""

from __future__ import annotations

import asyncio
import logging
from functools import lru_cache
from typing import Any, TypeVar

from agno.agent import Agent
from agno.models.openai import OpenAIChat
from pydantic import BaseModel

from app.core.config import settings

logger = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)


class AgentUnavailable(RuntimeError):
    """The model could not be reached or returned something unusable."""


def llm_available() -> bool:
    return settings.llm_enabled


@lru_cache(maxsize=1)
def build_model() -> OpenAIChat:
    kwargs: dict[str, Any] = {
        "id": settings.LLM_MODEL,
        "api_key": settings.OPENAI_API_KEY,
        "base_url": settings.LLM_BASE_URL,
        "timeout": settings.LLM_TIMEOUT_SECONDS,
    }
    # Reasoning models accept reasoning_effort and reject temperature; older chat
    # models are the other way round. One flag picks which is sent.
    if settings.LLM_SUPPORTS_EFFORT:
        kwargs["reasoning_effort"] = settings.LLM_EFFORT
    else:
        kwargs["temperature"] = 0.1
    # agno defaults the system message to OpenAI's newer "developer" role. That is
    # fine against api.openai.com, but every OpenAI-*compatible* proxy this project
    # has been pointed at (agentrouter, bazaarlink) 400s on it for non-OpenAI models
    # behind the proxy. "system" is the one role every provider accepts, so it is
    # forced here rather than left to change per provider.
    kwargs["role_map"] = {**OpenAIChat.default_role_map, "system": "system"}
    return OpenAIChat(**kwargs)


def make_agent(
    *,
    name: str,
    role: str,
    instructions: list[str],
    output_schema: type[BaseModel] | None = None,
) -> Agent:
    return Agent(
        name=name,
        role=role,
        model=build_model(),
        instructions=instructions,
        output_schema=output_schema,
        markdown=False,
        telemetry=False,
        retries=1,
    )


async def run_structured(agent: Agent, prompt: str, schema: type[T]) -> T:
    """Run an agent whose output_schema is `schema`; always returns an instance or raises AgentUnavailable.

    A provider can fail without raising - a WAF block or an error page comes back as
    ordinary response content, not an exception - so parsing it into `schema` is inside
    this same try/except rather than after it.
    """
    if not llm_available():
        raise AgentUnavailable("No LLM API key configured.")
    try:
        # httpx's read-timeout only fires on total silence between chunks - a provider that
        # trickles keep-alive bytes while effectively stalled never trips it - and agno's own
        # retry-on-any-exception loop (make_agent sets retries=1) can swallow a plain
        # asyncio.wait_for cancellation and just retry instead of propagating it, so the
        # ceiling never actually lands. Racing against a bare sleep and walking away from
        # the slow task (never awaiting it further) enforces the ceiling regardless of what
        # the library does internally - the orphaned task keeps running but nothing here
        # waits on it, so the patient is unblocked at settings.LLM_TIMEOUT_SECONDS no matter what.
        task = asyncio.ensure_future(agent.arun(prompt))
        done, pending = await asyncio.wait({task}, timeout=settings.LLM_TIMEOUT_SECONDS)
        if task in pending:
            task.cancel()
            task.add_done_callback(lambda t: t.exception() if not t.cancelled() else None)
            raise AgentUnavailable(f"{agent.name} exceeded the {settings.LLM_TIMEOUT_SECONDS}s timeout.")
        result = task.result()
        content = result.content
        if isinstance(content, schema):
            return content
        if isinstance(content, dict):
            return schema.model_validate(content)
        if isinstance(content, str):
            return schema.model_validate_json(content)
        raise AgentUnavailable(f"{agent.name} returned {type(content).__name__}, expected {schema.__name__}.")
    except AgentUnavailable:
        raise
    except TimeoutError as exc:
        raise AgentUnavailable(f"{agent.name} exceeded the {settings.LLM_TIMEOUT_SECONDS}s timeout.") from exc
    except Exception as exc:  # provider / network / validation
        raise AgentUnavailable(str(exc)) from exc