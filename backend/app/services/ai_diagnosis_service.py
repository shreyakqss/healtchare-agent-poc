"""The AI differential for the treating doctor. Drafted at pre-screening and on request, stored
as a ClinicalSummary of kind `ai_diagnosis`; the doctor accepts, edits or dismisses each
suggestion, and only accepted ones are offered for the consultation form. It never sets a
priority, never routes, and never reaches the patient projection - the patient only ever sees
what the doctor writes and signs."""

from __future__ import annotations

import uuid
from typing import Literal

from sqlalchemy.orm import Session

from app.agents import diagnosis_writer
from app.core.errors import NotFound, Unprocessable
from app.db import utcnow
from app.models import ClinicalSummary
from app.services import audit, case_repo, doctor_assistant_service

KIND = "ai_diagnosis"


async def generate(db: Session, case_id: uuid.UUID, actor: str) -> ClinicalSummary:
    """Raises AgentUnavailable when the model is down; the previous differential is kept."""
    context = doctor_assistant_service.case_context(db, case_id, with_diagnosis=False)
    result = await diagnosis_writer.write(context)
    summary = ClinicalSummary(
        case_id=case_id, kind=KIND, sections={**result.model_dump(), "decisions": {}},
        missing_information=result.missing_information, generated_by="llm",
    )
    db.add(summary)
    audit.record(db, case_id, actor, "ai_diagnosis.generated",
                 {"differentials": [d.condition for d in result.differentials]})
    db.commit()
    return summary


def decide(
    db: Session, case_id: uuid.UUID, index: int, decision: Literal["accept", "edit", "dismiss"],
    text: str | None, actor: str,
) -> ClinicalSummary:
    summary = case_repo.summary(db, case_id, KIND)
    if summary is None:
        raise NotFound("No AI diagnosis for this case.")
    differentials = summary.sections.get("differentials", [])
    if not 0 <= index < len(differentials):
        raise NotFound("No such suggestion.")
    if decision == "edit" and not (text or "").strip():
        raise Unprocessable("An edited diagnosis needs its wording.")
    condition = differentials[index]["condition"]
    entry = {"decision": decision, "by": actor, "at": utcnow().isoformat()}
    if decision == "edit":
        entry["text"] = text.strip()
    # Reassigned, not mutated: a JSONB column only notices a new value.
    summary.sections = {**summary.sections, "decisions": {**summary.sections.get("decisions", {}), str(index): entry}}
    audit.record(db, case_id, actor, f"ai_diagnosis.{decision}",
                 {"condition": condition, **({"text": entry["text"]} if decision == "edit" else {})})
    db.commit()
    return summary


async def proposed_in(reply: str) -> list[dict]:
    """The diagnoses one assistant reply puts forward, for the doctor to pick from. Raises
    AgentUnavailable when the model is down."""
    return [c.model_dump() for c in (await diagnosis_writer.extract(reply)).conditions]


def add(
    db: Session, case_id: uuid.UUID, condition: str, likelihood: str, supporting: list[str], actor: str,
) -> ClinicalSummary:
    """A diagnosis the doctor picked from the assistant chat. Added as already accepted - the doctor
    chose it - and marked `added_by: doctor` so it is never mistaken for the model's own ranking."""
    condition = condition.strip()
    if not condition:
        raise Unprocessable("A diagnosis needs its name.")
    summary = case_repo.summary(db, case_id, KIND)
    listed = {d["condition"].strip().lower() for d in (summary.sections if summary else {}).get("differentials", [])}
    if condition.lower() in listed:
        raise Unprocessable(f"{condition} is already in the differential.")
    if summary is None:
        summary = ClinicalSummary(
            case_id=case_id, kind=KIND, generated_by="doctor",
            sections={"differentials": [], "red_flags": [], "missing_information": [], "reasoning": "", "decisions": {}},
        )
        db.add(summary)
    differentials = list(summary.sections.get("differentials", []))
    differentials.append({
        "condition": condition, "likelihood": likelihood, "added_by": "doctor",
        "supporting": [p.strip() for p in supporting if p.strip()], "against": [], "tests": [], "management": [],
    })
    entry = {"decision": "accept", "by": actor, "at": utcnow().isoformat()}
    summary.sections = {
        **summary.sections, "differentials": differentials,
        "decisions": {**summary.sections.get("decisions", {}), str(len(differentials) - 1): entry},
    }
    audit.record(db, case_id, actor, "ai_diagnosis.added_from_assistant", {"condition": condition})
    db.commit()
    return summary
