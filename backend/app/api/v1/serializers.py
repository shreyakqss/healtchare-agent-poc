"""ORM rows -> response models. One place, so every endpoint agrees on shape."""

from __future__ import annotations

from collections import Counter
from datetime import timedelta

from sqlalchemy.orm import Session

from app.db import utcnow
from app.models import (
    AuditEvent,
    CareTask,
    ClinicalReview,
    ClinicalSummary,
    ConsultationNote,
    IntakeSession,
    MedicalAttachment,
    PatientCase,
    RoutingRecommendation,
    TriageResult,
    TriageRule,
)
from app.schemas.responses import (
    AttachmentResponse,
    AuditEventResponse,
    CareTaskResponse,
    CaseDetailResponse,
    CaseListItem,
    ClinicOverview,
    ConsultationNoteResponse,
    EntryResponse,
    FactResponse,
    ReviewResponse,
    RoutingResponse,
    SessionResponse,
    SlotResponse,
    SummaryResponse,
    TranscriptMessage,
    TriageResponse,
)
from app.services import case_repo, hospital_config


def session_out(db: Session, session: IntakeSession, case: PatientCase) -> SessionResponse:
    return SessionResponse(
        session_id=str(session.id), case_id=str(case.id), status=session.status,
        consent_status=session.consent_status, demographics=case.demographics or {},
        hms_linked=bool(case.hms_patient_id), missing_fields=case_repo.missing_fields(db, case.id),
    )


def attachment_out(a: MedicalAttachment) -> AttachmentResponse:
    return AttachmentResponse(
        id=str(a.id), kind=a.kind, filename=a.filename, mime_type=a.mime_type, size_bytes=a.size_bytes,
        has_text=bool(a.extracted_text), extracted_text=a.extracted_text, uploaded_by=a.uploaded_by, created_at=a.created_at,
    )


def triage_out(db: Session, t: TriageResult | None) -> TriageResponse | None:
    if t is None:
        return None
    rules = db.query(TriageRule).filter(TriageRule.code.in_(t.rule_codes or [])).all() if t.rule_codes else []
    return TriageResponse(
        priority=t.priority, rule_codes=list(t.rule_codes or []),
        rules=[{"code": r.code, "priority": r.priority, "action": r.action, "explanation": r.explanation, "version": r.version} for r in rules],
        warnings=list(t.warnings or []), evidence=list(t.evidence or []), created_at=t.created_at,
    )


def routing_out(r: RoutingRecommendation | None) -> RoutingResponse | None:
    if r is None:
        return None
    return RoutingResponse(
        department_id=r.department_id, department_name=r.department_name, doctor_id=r.doctor_id, doctor_name=r.doctor_name,
        appointment_type_id=r.appointment_type_id, appointment_type_label=r.appointment_type_label, rationale=r.rationale,
        matched_keywords=list(r.matched_keywords or []),
        suggested_slot=SlotResponse(**r.suggested_slot) if r.suggested_slot else None,
    )


def summary_out(s: ClinicalSummary | None) -> SummaryResponse | None:
    if s is None:
        return None
    return SummaryResponse(
        id=str(s.id), kind=s.kind, sections=s.sections or {}, evidence=list(s.evidence or []),
        missing_information=list(s.missing_information or []), generated_by=s.generated_by, created_at=s.created_at,
    )


def review_out(r: ClinicalReview | None) -> ReviewResponse | None:
    if r is None:
        return None
    return ReviewResponse(
        id=str(r.id), decision=r.decision, reviewer_id=r.reviewer_id, reviewer_role=r.reviewer_role,
        edits=r.edits or {}, comment=r.comment, created_at=r.created_at,
    )


def note_out(n: ConsultationNote) -> ConsultationNoteResponse:
    doctor = hospital_config.doctor_by_id(n.doctor_id)
    return ConsultationNoteResponse(
        id=str(n.id), doctor_id=n.doctor_id, doctor_name=doctor["name"] if doctor else None,
        consultation_mode=n.consultation_mode, notes=n.notes, prescription=n.prescription,
        follow_up_instructions=n.follow_up_instructions, created_at=n.created_at,
    )


def task_out(t: CareTask) -> CareTaskResponse:
    return CareTaskResponse(
        id=str(t.id), task_type=t.task_type, status=t.status, priority=t.priority, payload=t.payload or {},
        hms_reference=t.hms_reference, notes=t.notes, created_at=t.created_at,
    )


def audit_out(e: AuditEvent) -> AuditEventResponse:
    return AuditEventResponse(id=str(e.id), actor=e.actor, action=e.action, payload=e.payload or {}, created_at=e.created_at)


def case_detail(db: Session, case: PatientCase) -> CaseDetailResponse:
    session = case_repo.session_for(db, case)
    return CaseDetailResponse(
        case_id=str(case.id), session_id=str(case.session_id), status=session.status,
        consent_status=session.consent_status, channel=session.channel, hospital_id=case.hospital_id,
        demographics=case.demographics or {}, hms_patient_id=case.hms_patient_id,
        transcript=[TranscriptMessage(role=m.role, content=m.content, turn_index=m.turn_index) for m in case_repo.messages(db, session.id)],
        facts=[FactResponse(id=str(f.id), kind=f.kind, value=f.value, source=f.source, source_turn=f.source_turn, confidence=f.confidence)
               for f in case_repo.facts(db, case.id)],
        allergies_medications=[EntryResponse(id=str(e.id), kind=e.kind, name=e.name, reaction_or_dose=e.reaction_or_dose, source=e.source, source_turn=e.source_turn)
                               for e in case_repo.entries(db, case.id)],
        attachments=[attachment_out(a) for a in case_repo.attachments(db, case.id)],
        missing_fields=case_repo.missing_fields(db, case.id),
        triage=triage_out(db, case_repo.latest_triage(db, case.id)),
        routing=routing_out(case_repo.latest_routing(db, case.id)),
        prescreening_summary=summary_out(case_repo.summary(db, case.id, "prescreening")),
        review=review_out(case_repo.latest_review(db, case.id)),
        consultation_notes=[note_out(n) for n in case_repo.notes(db, case.id)],
        final_summary=summary_out(case_repo.summary(db, case.id, "final_visit")),
        care_tasks=[task_out(t) for t in case_repo.tasks(db, case.id)],
        created_at=case.created_at,
    )


def case_list(db: Session) -> list[CaseListItem]:
    items = []
    for case in db.query(PatientCase).order_by(PatientCase.created_at.desc()).all():
        session = db.get(IntakeSession, case.session_id)
        triage = case_repo.latest_triage(db, case.id)
        routing = case_repo.latest_routing(db, case.id)
        review = case_repo.latest_review(db, case.id)
        reason = next((f.value for f in case_repo.facts(db, case.id) if f.kind == "reason_for_visit"), None)
        last = db.query(AuditEvent).filter(AuditEvent.case_id == case.id).order_by(AuditEvent.created_at.desc()).first()
        items.append(CaseListItem(
            case_id=str(case.id), session_id=str(case.session_id), status=session.status if session else "UNKNOWN",
            priority=triage.priority if triage else None,
            department_id=routing.department_id if routing else None, department_name=routing.department_name if routing else None,
            doctor_id=routing.doctor_id if routing else None, doctor_name=routing.doctor_name if routing else None,
            chief_complaint=reason, demographics=case.demographics or {}, hms_patient_id=case.hms_patient_id,
            review_decision=review.decision if review else None, missing_count=len(case_repo.missing_fields(db, case.id)),
            created_at=case.created_at, updated_at=last.created_at if last else None,
        ))
    return items


def overview(items: list[CaseListItem]) -> ClinicOverview:
    today = utcnow() - timedelta(hours=24)
    return ClinicOverview(
        total=len(items),
        by_status=dict(Counter(i.status for i in items)),
        by_priority=dict(Counter(i.priority for i in items if i.priority)),
        by_department=dict(Counter(i.department_name for i in items if i.department_name)),
        awaiting_review=sum(1 for i in items if i.status == "NEEDS_REVIEW"),
        completed_today=sum(1 for i in items if i.status == "COMPLETED" and i.updated_at and i.updated_at >= today),
    )