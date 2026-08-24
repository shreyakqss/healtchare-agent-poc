"""Finalisation: visit summary -> draft care task (HMS appointment request) -> COMPLETED.

Gated by the API: only runs once a ClinicalReview with approve/edit exists and
consultation notes are recorded.
"""

from __future__ import annotations

import logging
import uuid

from agno.run.base import RunStatus
from agno.workflow import Step, Workflow
from agno.workflow.types import StepInput, StepOutput

from app.agents import AgentUnavailable
from app.agents.visit_reporter import VisitInputs, write_visit_summary
from app.db import db_session
from app.domain.lifecycle import CaseStatus
from app.integrations.hms import get_hms
from app.integrations.hms.schemas import AppointmentRequest
from app.models import CareTask, ClinicalSummary
from app.services import audit, case_repo, hospital_config, lifecycle
from app.workflows.common import case_id_from

logger = logging.getLogger(__name__)


async def write_summary(step_input: StepInput) -> StepOutput:
    case_id = case_id_from(step_input)
    with db_session() as db:
        facts = case_repo.facts(db, case_id)
        notes = case_repo.notes(db, case_id)
        routing = case_repo.latest_routing(db, case_id)
        latest = notes[-1]
        doctor = hospital_config.doctor_by_id(latest.doctor_id)
        inputs = VisitInputs(
            chief_complaint=next((f.value for f in facts if f.kind == "reason_for_visit"), "Not recorded"),
            department=routing.department_name if routing else None,
            doctor=doctor["name"] if doctor else latest.doctor_id,
            consultation_mode=latest.consultation_mode,
            notes="\n\n".join(n.notes for n in notes),
            prescription=latest.prescription,
            follow_up=latest.follow_up_instructions,
        )
        try:
            sections = (await write_visit_summary(inputs)).model_dump()
            generated_by = "llm"
        except AgentUnavailable as exc:
            logger.warning("Visit reporter unavailable: %s", exc)
            sections = {
                "visit_reason": inputs.chief_complaint,
                "consultation_overview": f"{inputs.consultation_mode.replace('_', ' ').title()} consultation with {inputs.doctor}.",
                "doctor_notes_summary": inputs.notes,
                "follow_up_instructions": [inputs.follow_up] if inputs.follow_up else [],
                "patient_friendly_summary": inputs.notes,
            }
            generated_by = "fallback"
        sections["prescription"] = latest.prescription
        sections["consultation_mode"] = latest.consultation_mode
        sections["doctor"] = inputs.doctor
        sections["department"] = inputs.department
        db.add(ClinicalSummary(case_id=case_id, kind="final_visit", sections=sections, generated_by=generated_by))
        audit.record(db, case_id, "system:visit_reporter", "summary.final_generated", {"generated_by": generated_by})
    return StepOutput(content={"generated_by": generated_by})


async def create_care_task(step_input: StepInput) -> StepOutput:
    """Draft only. The HMS receives an appointment *request*, never a booking."""
    case_id = case_id_from(step_input)
    with db_session() as db:
        case = case_repo.case_or_404(db, case_id)
        triage = case_repo.latest_triage(db, case_id)
        routing = case_repo.latest_routing(db, case_id)
        review = case_repo.latest_review(db, case_id)
        notes = case_repo.notes(db, case_id)
        priority = triage.priority if triage else "low"
        follow_up = notes[-1].follow_up_instructions if notes else None

        reference = None
        if routing:
            result = get_hms().request_appointment(AppointmentRequest(
                case_id=str(case_id), patient_mrn=case.hms_patient_id,
                patient_name=(case.demographics or {}).get("name", "Unnamed patient"),
                department_id=routing.department_id, practitioner_id=routing.doctor_id,
                appointment_type_id=routing.appointment_type_id, priority=priority,
                preferred_slot_id=(routing.suggested_slot or {}).get("id"),
                reason=follow_up or "Follow-up after consultation",
            ))
            reference = result.reference
            slot = result.slot.model_dump(mode="json") if result.slot else None
        else:
            slot = None

        task = CareTask(
            case_id=case_id, task_type="follow_up" if follow_up else "schedule_appointment",
            status="draft", priority=priority, hms_reference=reference,
            payload={
                "department": routing.department_name if routing else None,
                "doctor": routing.doctor_name if routing else None,
                "appointment_type": routing.appointment_type_label if routing else None,
                "slot": slot,
                "approved_by": review.reviewer_id if review else None,
                "edits_applied": bool(review and review.edits),
            },
            notes=follow_up,
        )
        db.add(task)
        audit.record(db, case_id, "system:task_agent", "care_task.drafted",
                     {"task_type": task.task_type, "hms_reference": reference, "status": "draft"})
    return StepOutput(content={"hms_reference": reference})


async def complete(step_input: StepInput) -> StepOutput:
    case_id = case_id_from(step_input)
    with db_session() as db:
        case = case_repo.case_or_404(db, case_id)
        session = case_repo.session_for(db, case)
        lifecycle.transition(db, session, CaseStatus.COMPLETED, "system:finalize", case_id)
    return StepOutput(content={"status": CaseStatus.COMPLETED})


finalize_workflow = Workflow(
    name="finalize",
    description="Visit summary and draft care task after clinician approval.",
    steps=[
        Step(name="write_summary", executor=write_summary),
        Step(name="create_care_task", executor=create_care_task),
        Step(name="complete", executor=complete),
    ],
    telemetry=False,
)


async def run_finalize(case_id: uuid.UUID) -> None:
    try:
        result = await finalize_workflow.arun(input={"case_id": str(case_id)})
        if result.status != RunStatus.completed:
            raise RuntimeError(f"Workflow ended with status {result.status}: {result.content}")
    except Exception as exc:
        logger.exception("Finalize failed for %s", case_id)
        with db_session() as db:
            case = case_repo.case_or_404(db, case_id)
            session = case_repo.session_for(db, case)
            audit.record(db, case_id, "system:finalize", "workflow.failed", {"error": str(exc)[:500]})
            lifecycle.transition(db, session, CaseStatus.FAILED, "system:finalize", case_id)
        raise