"""Case context for the doctor assistant chat. The transcript itself is not persisted - the
frontend replays it on every turn, the same way the intake composer keeps its own history."""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.agents import doctor_assistant
from app.services import case_repo


def _case_context(db: Session, case_id: uuid.UUID) -> str:
    facts = case_repo.facts(db, case_id)
    entries = case_repo.clinical_entries(db, case_id)
    triage = case_repo.latest_triage(db, case_id)
    routing = case_repo.latest_routing(db, case_id)
    notes = case_repo.notes(db, case_id)

    lines: list[str] = []
    # Joined, not just the last one: a single turn can name several problems at once
    # ("fever and body ache") as separate reason_for_visit facts - a doctor needs all of them.
    reasons = [f.value for f in facts if f.kind == "reason_for_visit"]
    reason = ", ".join(dict.fromkeys(reasons)) or None
    if reason:
        lines.append(f"Chief complaint: {reason}")
    symptoms = [f.value for f in facts if f.kind == "symptom"]
    if symptoms:
        lines.append(f"Symptoms: {', '.join(symptoms)}")
    history = [f.value for f in facts if f.kind == "history"]
    if history:
        lines.append(f"History: {', '.join(history)}")
    if entries:
        lines.append(
            "Allergies/medications: "
            + "; ".join(f"{e.kind} - {e.name}" + (f" ({e.reaction_or_dose})" if e.reaction_or_dose else "") for e in entries)
        )
    if triage:
        lines.append(f"Administrative priority: {triage.priority} ({', '.join(triage.rule_codes)})")
    if routing:
        lines.append(f"Routed to: {routing.department_name}" + (f" / {routing.doctor_name}" if routing.doctor_name else ""))
    if notes:
        lines.append(f"Consultation notes: {notes[-1].notes}")
    return "\n".join(lines) or "No case details recorded yet."


async def chat(
    db: Session, case_id: uuid.UUID, doctor_context: str, message: str, transcript: list[dict[str, str]]
) -> str:
    context = _case_context(db, case_id)
    return await doctor_assistant.answer(message, doctor_context, context, transcript)
