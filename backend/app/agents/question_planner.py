"""Question planner: phrases the single next intake question.

The model chooses wording only. Which field to ask, and when intake is
finished, is decided in code (see app/services/intake_turn.py).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from functools import lru_cache

from agno.run.agent import RunEvent

from app.agents.llm import AgentUnavailable, llm_available, make_agent
from app.domain.intake_fields import FIELD_PROMPTS

INSTRUCTIONS = [
    "You are the intake assistant for a medical clinic, talking to a patient.",
    "Ask exactly ONE short, plain-language question to collect the field the caller names. Be warm and brief.",
    "Never diagnose, never suggest treatment, never interpret results, never say how urgent the case is.",
    "If the patient describes a life-threatening emergency, your question must tell them to contact "
    "emergency services immediately.",
    "Do not repeat or reword any question already asked, and do not ask about anything already on file.",
    "Reply with the question itself and nothing else: no preamble, no quotes, no list.",
]


@dataclass
class PlannerContext:
    field: str
    outstanding: list[str]
    transcript: list[dict[str, str]]
    on_file: list[str] = field(default_factory=list)
    patient_name: str | None = None


@lru_cache(maxsize=1)
def _agent():
    return make_agent(
        name="Question Planner",
        role="Phrase the next intake question",
        instructions=INSTRUCTIONS,
    )


def fallback_question(ctx: PlannerContext) -> str:
    return f"Could you tell me {FIELD_PROMPTS.get(ctx.field, ctx.field)}?"


def _prompt(ctx: PlannerContext) -> str:
    history = "\n".join(f"{m['role']}: {m['content']}" for m in ctx.transcript[-8:]) or "(nothing yet)"
    asked = [m["content"] for m in ctx.transcript if m["role"] == "assistant"]
    lines = [
        f"Conversation so far:\n{history}",
        "Already on file - do NOT ask about any of this again:\n"
        + ("\n".join(f"- {x}" for x in ctx.on_file) or "- (nothing yet)"),
        "Questions already asked - do not repeat or reword:\n"
        + ("\n".join(f"- {q}" for q in asked) or "- (none yet)"),
        f"Still missing: {', '.join(FIELD_PROMPTS.get(f, f) for f in ctx.outstanding)}.",
        f"Ask one question about: {FIELD_PROMPTS.get(ctx.field, ctx.field)}.",
    ]
    if ctx.patient_name:
        lines.append(f"The patient's name is {ctx.patient_name}; you may use it once, naturally.")
    return "\n\n".join(lines)


async def plan(ctx: PlannerContext, on_token: Callable[[str], None] | None = None) -> str:
    """Stream the question through `on_token`; return the full text. Raises AgentUnavailable."""
    if not llm_available():
        raise AgentUnavailable("No LLM API key configured.")
    text = ""
    try:
        async for event in _agent().arun(_prompt(ctx), stream=True):
            if event.event == RunEvent.run_content and isinstance(event.content, str) and event.content:
                text += event.content
                if on_token:
                    on_token(event.content)
    except Exception as exc:
        raise AgentUnavailable(str(exc)) from exc
    text = text.strip().strip('"')
    if not text:
        raise AgentUnavailable("The planner produced an empty question.")
    return text