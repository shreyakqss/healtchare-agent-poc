"""Task / Report Agent — final visit summary and the draft care task.

Runs only after a clinician has approved the case. The care task it produces is
explicitly a **draft**: nothing here books an appointment or touches an external
system.
"""
import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from models import (
    AuditEvent,
    ClinicalReview,
    ClinicalSummary,
    ConsultationNote,
    IntakeSession,
    PatientCase,
    RoutingRecommendation,
    TriageResult,
)
from schemas.agent_outputs import VisitSummary, json_schema
from services.llm_client import LLMError, llm

logger = logging.getLogger(__name__)

SYSTEM = """You write the final visit summary after a clinician has completed a \
consultation and signed off on the case.

You are a documentation assistant. Rules:
- Base the summary on the clinician's own notes and the recorded case facts.
- Never add a diagnosis, treatment, or recommendation the clinician did not write.
- Never contradict or reinterpret the clinician's notes.
- Follow-up instructions must come from the clinician's notes, not from you.

Write plainly, for a summary the patient may also read."""


async def finalise_visit(db: Session, case_id) -> tuple[ClinicalSummary, dict]:
    """Generate the final visit summary and a draft care task."""
    case = db.get(PatientCase, case_id)
    if case is None:
        raise ValueError(f"Case {case_id} not found.")

    notes = (
        db.query(ConsultationNote)
        .filter(ConsultationNote.case_id == case_id)
        .order_by(ConsultationNote.created_at)
        .all()
    )
    prescreening = (
        db.query(ClinicalSummary)
        .filter(
            ClinicalSummary.case_id == case_id,
            ClinicalSummary.kind == "prescreening",
        )
        .order_by(ClinicalSummary.created_at.desc())
        .first()
    )
    routing = (
        db.query(RoutingRecommendation)
        .filter(RoutingRecommendation.case_id == case_id)
        .order_by(RoutingRecommendation.created_at.desc())
        .first()
    )
    triage = (
        db.query(TriageResult)
        .filter(TriageResult.case_id == case_id)
        .order_by(TriageResult.created_at.desc())
        .first()
    )
    review = (
        db.query(ClinicalReview)
        .filter(ClinicalReview.case_id == case_id)
        .order_by(ClinicalReview.created_at.desc())
        .first()
    )

    note_text = "\n\n".join(
        f"[{n.doctor_id}] {n.notes}"
        + (f"\nFollow-up: {n.follow_up_instructions}" if n.follow_up_instructions else "")
        for n in notes
    ) or "(no consultation notes recorded)"

    prescreen_context = ""
    if prescreening:
        sections = prescreening.sections or {}
        prescreen_context = (
            f"Chief complaint: {sections.get('chief_complaint', 'not recorded')}\n"
            f"Reported symptoms: {', '.join(sections.get('reported_symptoms', [])) or 'none'}\n"
        )

    user = f"""Pre-screening record:
{prescreen_context or '(none)'}

Department seen: {routing.specialty if routing else 'not recorded'}
Appointment type: {routing.appointment_type if routing else 'not recorded'}

Clinician's consultation notes:
{note_text}

Write the final visit summary."""

    try:
        raw = await llm.chat_json(SYSTEM, user, json_schema(VisitSummary))
        summary = VisitSummary.model_validate(raw)
        sections = summary.model_dump()
    except (LLMError, ValueError) as exc:
        logger.warning("Visit summary fell back to a plain record: %s", exc)
        sections = {
            "visit_reason": (prescreening.sections or {}).get(
                "chief_complaint", "Not recorded"
            )
            if prescreening
            else "Not recorded",
            "consultation_overview": "Narrative generation was unavailable.",
            "doctor_notes_summary": note_text,
            "follow_up_instructions": [
                n.follow_up_instructions for n in notes if n.follow_up_instructions
            ],
            "administrative_notes": "",
        }

    # Draft only. Creating this does not book anything.
    draft_task = {
        "type": "care_task",
        "status": "draft",
        "department_id": routing.department_id if routing else None,
        "doctor_id": routing.doctor_id if routing else None,
        "appointment_type": routing.appointment_type if routing else None,
        "priority": triage.priority if triage else None,
        "requires_scheduling_confirmation": True,
        "created_from_review": str(review.id) if review else None,
    }
    sections["draft_care_task"] = draft_task

    record = ClinicalSummary(
        case_id=case_id,
        kind="final_visit",
        sections=sections,
        evidence=list(triage.evidence or []) if triage else [],
        missing_information=[],
    )
    db.add(record)

    session = db.get(IntakeSession, case.session_id)
    if session is not None:
        session.status = "COMPLETED"
        session.completed_at = datetime.now(timezone.utc)

    db.add(
        AuditEvent(
            case_id=case_id,
            actor="system:task_report_agent",
            action="visit.finalised",
            payload={"draft_task": draft_task, "note_count": len(notes)},
        )
    )
    db.commit()
    db.refresh(record)
    return record, draft_task
