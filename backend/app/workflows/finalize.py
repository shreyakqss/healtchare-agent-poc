"""Finalisation: visit summary -> draft care task (HMS appointment request) -> COMPLETED.

Gated by the API: only runs once a ClinicalReview with approve/edit exists and
consultation notes are recorded.
"""

from __future__ import annotations

import asyncio
import logging
import uuid

from agno.run.base import RunStatus
from agno.workflow import Workflow
from agno.workflow.types import StepInput, StepOutput

from app.agents import AgentUnavailable
from app.agents.visit_reporter import VisitInputs, write_visit_summary
from app.core.tracing import case_trace
from app.db import db_session
from app.domain.lifecycle import CaseStatus
from app.integrations.hms import get_hms
from app.integrations.hms.schemas import AppointmentRequest
from app.models import CareTask, ClinicalSummary
from app.services import audit, case_repo, hospital_config, lifecycle, workflow_operations
from app.services.hms import forward_audit_note, push_document_with_retry, reviewed_payload
from app.workflows.common import case_id_from, complete_step, completed_step, step, workflow_input

logger = logging.getLogger(__name__)


async def write_summary(step_input: StepInput) -> StepOutput:
    case_id = case_id_from(step_input)
    with db_session() as db:
        if cached := completed_step(db, step_input, "write_final_summary"):
            return StepOutput(content=cached)
        facts = case_repo.facts(db, case_id)
        notes = case_repo.notes(db, case_id)
        routing = case_repo.latest_routing(db, case_id)
        latest = notes[-1]
        # doctor_id is the verified hospital-system identity (an OpenEMR Practitioner UUID),
        # not a local hospital_config.yaml doctor id - doctor_name (captured at write-time) is
        # the display name; the YAML lookup is kept only as a fallback for a ConsultationNote
        # row written before doctor_name existed.
        doctor = hospital_config.doctor_by_id(latest.doctor_id)
        display_doctor = latest.doctor_name or (doctor["name"] if doctor else latest.doctor_id)
        inputs = VisitInputs(
            chief_complaint=next((f.value for f in facts if f.kind == "reason_for_visit"), "Not recorded"),
            department=routing.department_name if routing else None,
            doctor=display_doctor,
            consultation_mode=latest.consultation_mode,
            notes="\n\n".join(n.notes for n in notes),
            prescription=latest.prescription,
            follow_up=latest.follow_up_instructions,
        )
        try:
            sections = (await write_visit_summary(inputs)).model_dump()
            generated_by = "llm"
        except AgentUnavailable as exc:
            logger.warning("Visit reporter unavailable (%s)", type(exc).__name__)
            sections = {
                "visit_reason": inputs.chief_complaint,
                "consultation_overview": f"{inputs.consultation_mode.replace('_', ' ').title()} consultation with {inputs.doctor}.",
                "doctor_notes_summary": "Automated summary unavailable; refer to the clinician-authored consultation note.",
                "follow_up_instructions": [inputs.follow_up] if inputs.follow_up else [],
                "patient_friendly_summary": "Your visit summary is not available yet. Contact the clinic for reviewed instructions.",
            }
            generated_by = "fallback"
        sections["prescription"] = latest.prescription
        sections["consultation_mode"] = latest.consultation_mode
        sections["doctor"] = inputs.doctor
        sections["department"] = inputs.department
        summary = case_repo.summary(db, case_id, "final_visit")
        if summary is None:
            db.add(ClinicalSummary(case_id=case_id, kind="final_visit", sections=sections, generated_by=generated_by))
            audit.record(db, case_id, "system:visit_reporter", "summary.final_generated", {"generated_by": generated_by})
        else:
            sections, generated_by = summary.sections, summary.generated_by

        case = case_repo.case_or_404(db, case_id)
        if case.hms_patient_id:
            text = "\n".join(f"{key}: {value}" for key, value in sections.items())
            push_op, already_pushed = workflow_operations.begin_external(
                db, case_id, f"case:{case_id}:visit-summary:v1", "hms.visit_summary"
            )
            if already_pushed:
                reference = push_op.result.get("reference")
            else:
                reference, error_type = await asyncio.to_thread(
                    push_document_with_retry,
                    get_hms(), case.hms_patient_id, title="Visit Summary", content=text.encode("utf-8"), content_type="text/plain",
                )
                workflow_operations.finish_external(
                    db,
                    push_op,
                    result={"reference": reference} if reference else None,
                    error_code=error_type if reference is None else None,
                )
                if reference is None:
                    audit.record(db, case_id, "system:visit_reporter", "summary.push_to_hms_failed", {"error_type": error_type})
                    raise RuntimeError("HMS visit-summary write failed")
                audit.record(db, case_id, "system:visit_reporter", "summary.pushed_to_hms", {"hms_reference": reference})

            sync_op, already_synced = workflow_operations.begin_external(
                db, case_id, f"case:{case_id}:reviewed-intake:v1", "hms.reviewed_intake"
            )
            if not already_synced:
                error_type = None
                try:
                    await asyncio.to_thread(get_hms().sync_reviewed_intake, case.hms_patient_id, reviewed_payload(db, case))
                except Exception as exc:
                    error_type = type(exc).__name__
                workflow_operations.finish_external(db, sync_op, error_code=error_type)
                if error_type:
                    audit.record(db, case_id, "system:hms_sync", "reviewed_intake.push_to_hms_failed", {"error_type": error_type})
                    raise RuntimeError("HMS reviewed-intake write failed")
                audit.record(db, case_id, "system:hms_sync", "reviewed_intake.pushed_to_hms", {})
        result = {"generated_by": generated_by}
        complete_step(db, step_input, "write_final_summary", result)
    return StepOutput(content=result)


async def create_care_task(step_input: StepInput) -> StepOutput:
    """Draft only. The HMS receives an appointment *request*, never a booking."""
    case_id = case_id_from(step_input)
    finalizer_id = workflow_input(step_input).get("finalizer_id")
    finalizer_name = workflow_input(step_input).get("finalizer_name")
    with db_session() as db:
        if cached := completed_step(db, step_input, "create_care_task"):
            return StepOutput(content=cached)
        case = case_repo.case_or_404(db, case_id)
        triage = case_repo.latest_triage(db, case_id)
        routing = case_repo.latest_routing(db, case_id)
        review = case_repo.latest_review(db, case_id)
        notes = case_repo.notes(db, case_id)
        priority = triage.priority if triage else "low"
        follow_up = notes[-1].follow_up_instructions if notes else None

        reference, slot, request_error = None, None, None
        if routing:
            request = AppointmentRequest(
                case_id=str(case_id), patient_mrn=case.hms_patient_id,
                patient_name=case_repo.demographics(db, case_id).get("name", "Unnamed patient"),
                department_id=routing.department_id, practitioner_id=routing.doctor_id,
                appointment_type_id=routing.appointment_type_id, priority=priority,
                preferred_slot_id=(routing.suggested_slot or {}).get("id"),
                reason=follow_up or "Follow-up after consultation",
            )
            # The task is a draft either way: an HMS that refuses the request (no Appointment
            # write on this install, network down) leaves the draft for staff to place by hand.
            request_op, already_requested = workflow_operations.begin_external(
                db, case_id, f"case:{case_id}:appointment-request:v1", "hms.appointment_request"
            )
            if already_requested:
                reference = request_op.result.get("reference")
                slot = request_op.result.get("slot")
            else:
                try:
                    appointment_result = await asyncio.to_thread(get_hms().request_appointment, request)
                    reference = appointment_result.reference
                    slot = appointment_result.slot.model_dump(mode="json") if appointment_result.slot else None
                    workflow_operations.finish_external(
                        db, request_op, result={"reference": reference, "slot": slot}
                    )
                except Exception as exc:  # noqa: BLE001 - draft remains actionable without HMS
                    request_error = type(exc).__name__
                    workflow_operations.finish_external(db, request_op, error_code=request_error)
                    logger.warning("HMS appointment request failed (%s)", request_error)

        task = CareTask(
            case_id=case_id, task_type="follow_up" if follow_up else "schedule_appointment",
            status="draft", priority=priority, hms_reference=reference,
            payload={
                "department": routing.department_name if routing else None,
                "doctor": routing.doctor_name if routing else None,
                "appointment_type": routing.appointment_type_label if routing else None,
                "slot": slot,
                # "approved_by" stays the clinician who approved the ClinicalReview - a
                # distinct action from finalizing (a different clinician could plausibly
                # trigger finalize). The verified finalizer identity is recorded separately
                # as "finalized_by" rather than overloading approved_by's existing meaning.
                "approved_by": review.reviewer_id if review else None,
                "edits_applied": bool(review and review.edits),
                "finalized_by": finalizer_id,
                "finalized_by_name": finalizer_name,
            },
            notes=follow_up,
        )
        db.add(task)
        audit.record(db, case_id, "system:task_agent", "care_task.drafted",
                     {"task_type": task.task_type, "hms_reference": reference, "status": "draft"})
        if request_error:
            audit.record(db, case_id, "system:hms_sync", "care_task.hms_request_failed", {"error_type": request_error})
        result = {"hms_reference": reference}
        complete_step(db, step_input, "create_care_task", result)
    return StepOutput(content=result)


async def complete(step_input: StepInput) -> StepOutput:
    case_id = case_id_from(step_input)
    finalizer_id = workflow_input(step_input).get("finalizer_id")
    actor = f"doctor:{finalizer_id}" if finalizer_id else "system:finalize"
    with db_session() as db:
        if cached := completed_step(db, step_input, "complete"):
            return StepOutput(content=cached)
        case = case_repo.case_or_404(db, case_id)
        session = case_repo.session_for(db, case)
        lifecycle.transition(db, session, CaseStatus.COMPLETED, actor, case_id, commit=False)
        # Blocking HTTP; same event-loop concern as the push_document_with_retry calls above.
        await asyncio.to_thread(forward_audit_note, case, actor, "case.completed", {"status": CaseStatus.COMPLETED})
        result = {"status": CaseStatus.COMPLETED}
        complete_step(db, step_input, "complete", result)
    return StepOutput(content=result)


finalize_workflow = Workflow(
    name="finalize",
    description="Visit summary and draft care task after clinician approval.",
    steps=[
        step("write_summary", write_summary),
        step("create_care_task", create_care_task),
        step("complete", complete),
    ],
    telemetry=False,
)


async def run_finalize(
    case_id: uuid.UUID,
    finalizer_id: str | None = None,
    finalizer_name: str | None = None,
    *,
    job_id: uuid.UUID | None = None,
    mark_failed: bool = True,
) -> None:
    try:
        with case_trace("workflow.finalize", case_id):
            result = await finalize_workflow.arun(
                input={
                    "case_id": str(case_id),
                    "finalizer_id": finalizer_id,
                    "finalizer_name": finalizer_name,
                    "job_id": str(job_id) if job_id else None,
                }
            )
        if result.status != RunStatus.completed:
            raise RuntimeError(f"Workflow ended with status {result.status}: {result.content}")
    except Exception as exc:
        logger.error("Finalize failed (%s)", type(exc).__name__)
        if mark_failed:
            with db_session() as db:
                case = case_repo.case_or_404(db, case_id)
                session = case_repo.session_for(db, case)
                audit.record(db, case_id, "system:finalize", "workflow.failed", {"error_type": type(exc).__name__})
                lifecycle.transition(db, session, CaseStatus.FAILED, "system:finalize", case_id)
        raise
