"""Final visit summary after a clinician has consulted and approved."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from app.agents.llm import make_agent, run_structured
from app.agents.schemas import VisitSummary

INSTRUCTIONS = [
    "You write the final visit summary after a clinician has completed a consultation and signed off.",
    "Base the summary on the clinician's own notes and the recorded case facts.",
    "Never add a diagnosis, treatment or recommendation the clinician did not write.",
    "Never contradict or reinterpret the clinician's notes.",
    "Follow-up instructions must come from the clinician's notes, not from you.",
    "Write plainly, for a summary the patient may also read.",
]


@dataclass
class VisitInputs:
    chief_complaint: str
    department: str | None
    doctor: str | None
    consultation_mode: str
    notes: str
    prescription: str | None
    follow_up: str | None


@lru_cache(maxsize=1)
def _agent():
    return make_agent(
        name="Visit Reporter",
        role="Write the final visit summary",
        instructions=INSTRUCTIONS,
        output_schema=VisitSummary,
    )


def _prompt(i: VisitInputs) -> str:
    return (
        f"Chief complaint at intake: {i.chief_complaint}\n"
        f"Department: {i.department or 'n/a'}; Doctor: {i.doctor or 'n/a'}; Mode: {i.consultation_mode}\n\n"
        f"Clinician notes:\n{i.notes}\n\n"
        f"Prescription (clinician's words): {i.prescription or '(none)'}\n"
        f"Follow-up instructions (clinician's words): {i.follow_up or '(none)'}\n\n"
        "Write the visit summary."
    )


async def write_visit_summary(inputs: VisitInputs) -> VisitSummary:
    return await run_structured(_agent(), _prompt(inputs), VisitSummary)