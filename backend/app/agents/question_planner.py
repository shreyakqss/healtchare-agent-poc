"""Question planner: phrases the single next intake question.

The model chooses wording only. Which field to ask, and when intake is
finished, is decided in code (see app/services/intake_service.py).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from functools import lru_cache

from app.agents.llm import make_agent, stream_text
from app.domain.intake_fields import FIELD_PROMPTS

INSTRUCTIONS = [
    "You are the intake assistant for a medical clinic, talking to a patient.",
    "Ask exactly ONE short, plain-language question to collect the field the caller names. Be warm and brief.",
    "Never diagnose, suggest treatment, interpret results or assign a triage priority.",
    "If the patient describes a life-threatening emergency, your question must tell them to contact "
    "emergency services immediately.",
    "Do not repeat or reword any question already asked, and do not ask about anything already on file.",
    "Reply with the question itself and nothing else: no preamble, no quotes, no list.",
    "Never use an em dash (—); use a comma, period or parenthesis instead.",
]


@dataclass
class PlannerContext:
    field: str
    outstanding: list[str]
    transcript: list[dict[str, str]]
    on_file: list[str] = field(default_factory=list)
    patient_name: str | None = None
    medication_candidates: list[str] = field(default_factory=list)


@lru_cache(maxsize=1)
def _agent():
    return make_agent(
        name="Question Planner",
        role="Phrase the next intake question",
        instructions=INSTRUCTIONS,
    )


def fallback_question(ctx: PlannerContext) -> str:
    if ctx.field == "medication" and ctx.medication_candidates:
        return (
            f"Your uploaded prescription lists: {', '.join(ctx.medication_candidates)}. "
            "Are you currently taking these? Anything else?"
        )
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
    if ctx.field == "medication" and ctx.medication_candidates:
        lines.append(
            "Their uploaded prescription lists: " + ", ".join(ctx.medication_candidates)
            + ". Ask whether they are currently taking these, and whether they take anything else."
        )
    return "\n\n".join(lines)


async def plan(ctx: PlannerContext, on_token: Callable[[str], None] | None = None) -> str:
    """Stream the question through `on_token`; return the full text. Raises AgentUnavailable."""
    return (await stream_text(_agent(), _prompt(ctx), on_token)).strip('"')
