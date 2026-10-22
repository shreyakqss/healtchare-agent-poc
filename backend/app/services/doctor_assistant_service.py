"""Case context for the doctor assistant chat. The transcript itself is not persisted - the
frontend replays it on every turn, the same way the intake composer keeps its own history."""

from __future__ import annotations

import re
import uuid

from sqlalchemy.orm import Session

from app.agents import doctor_assistant
from app.domain import scheduling
from app.models import PatientCase
from app.services import case_repo

# The intake conversation is the patient's own account; cap it so a long chat cannot crowd out
# the question (the newest turns are kept).
MAX_TRANSCRIPT_CHARS = 6000


def _case_context(db: Session, case_id: uuid.UUID) -> str:
    """Everything the treating doctor can already see on the case page, as plain lines for the
    assistant: who the patient is (age/gender, never name or contact), what they reported and in
    which words, how the clinic's rules triaged and routed it, mismatches against their records,
    the review and consultation so far. Uploaded document text is not included."""
    case = case_repo.case_or_404(db, case_id)
    facts = case_repo.facts(db, case_id)
    captured = case_repo.captured_fields(db, case_id)
    entries = case_repo.clinical_entries(db, case_id)
    triage = case_repo.latest_triage(db, case_id)
    routing = case_repo.latest_routing(db, case_id)
    review = case_repo.latest_review(db, case_id)
    notes = case_repo.notes(db, case_id)
    prescreen = case_repo.summary(db, case_id, "prescreening")

    lines: list[str] = []
    patient = ", ".join(f"{k} {v[0]}" for k in ("age", "gender") if (v := captured.get(k)))
    if patient:
        lines.append(f"Patient: {patient}")
    if case.emergency_flagged_at:
        lines.append(
            "EMERGENCY: a red-flag rule matched during intake; the patient was told to call an "
            f"ambulance now ({case.emergency_flagged_at:%Y-%m-%d %H:%M} UTC) and was not offered a booking."
        )
    # Joined, not just the last one: a single turn can name several problems at once
    # ("fever and body ache") as separate reason_for_visit facts - a doctor needs all of them.
    for label, kind in (("Chief complaint", "reason_for_visit"), ("Symptoms", "symptom"),
                        ("Duration", "duration"), ("History (patient-reported)", "history")):
        values = list(dict.fromkeys(captured.get(kind) or [f.value for f in facts if f.kind == kind]))
        if values:
            lines.append(f"{label}: {', '.join(values)}")
    if entries:
        lines.append(
            "Allergies/medications: "
            + "; ".join(f"{e.kind} - {e.name}" + (f" ({e.reaction_or_dose})" if e.reaction_or_dose else "") for e in entries)
        )
    if triage:
        lines.append(f"Administrative priority: {triage.priority} ({', '.join(triage.rule_codes)})")
    if routing:
        lines.append(f"Routed to: {routing.department_name}" + (f" / {routing.doctor_name}" if routing.doctor_name else ""))
        booked = scheduling.chosen_slot(routing.slot_options or [], routing.selected_slot_id, routing.suggested_slot)
        if case.hms_appointment_id and booked:
            lines.append(f"Appointment booked: {booked.get('start')}")
    if mismatches := case_repo.discrepancies(db, case_id):
        lines.append("Mismatches with records: " + "; ".join(
            f"{d.field_or_topic}: patient said '{d.patient_stated}', record says '{d.document_says}'" for d in mismatches))
    if prescreen and (sections := prescreen.sections or {}):
        if brief := sections.get("context_for_clinician"):
            lines.append(f"Pre-screening brief: {brief}")
        if missing := prescreen.missing_information:
            lines.append(f"Not collected: {'; '.join(missing)}")
    if review:
        lines.append(f"Clinician review: {review.decision}" + (f" - {review.comment}" if review.comment else ""))
        if review.edits:
            lines.append(f"Reviewer corrections: {review.edits}")
    for n, note in enumerate(notes, 1):
        lines.append(f"Consultation note {n}: {note.notes}")
    if transcript := _intake_transcript(db, case):
        lines.append(f"Intake conversation (patient's own words):\n{transcript}")
    return "\n".join(lines) or "No case details recorded yet."


def _intake_transcript(db: Session, case: PatientCase) -> str:
    """The clinical chat only: turn 0 is the identity form (name, birth date, contact, address),
    which the assistant never needs, and the patient's name is masked where the chat used it."""
    session = case_repo.session_for(db, case)
    names = [part for part in (case_repo.demographics(db, case.id).get("name") or "").split() if len(part) > 1]
    turns = []
    for m in case_repo.messages(db, session.id):
        if m.turn_index == 0:
            continue
        text = m.content
        for part in names:
            text = re.sub(rf"\b{re.escape(part)}\b", "[patient]", text, flags=re.I)
        turns.append(f"{m.role}: {text}")
    kept: list[str] = []
    for turn in reversed(turns):
        if sum(len(t) for t in kept) + len(turn) > MAX_TRANSCRIPT_CHARS:
            kept.append("(earlier messages omitted)")
            break
        kept.append(turn)
    return "\n".join(reversed(kept))


async def chat(
    db: Session, case_id: uuid.UUID, doctor_context: str, message: str, transcript: list[dict[str, str]]
) -> str:
    context = _case_context(db, case_id)
    return await doctor_assistant.answer(message, doctor_context, context, transcript)
