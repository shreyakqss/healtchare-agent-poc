"""ORM rows -> response models. One place, so every endpoint agrees on shape."""

from __future__ import annotations

import uuid
from collections import defaultdict

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.domain import intake_fields
from app.models import (
    AllergyMedication,
    AuditEvent,
    CareTask,
    ClinicalReview,
    ClinicalSummary,
    ConsultationNote,
    IntakeSession,
    MedicalAttachment,
    PatientCase,
    PatientFact,
    RoutingRecommendation,
    TriageResult,
    TriageRule,
)
from app.schemas.responses import (
    ActiveIntakeResponse,
    AttachmentResponse,
    AuditEventResponse,
    CareTaskResponse,
    CaseDetailResponse,
    CaseListItem,
    ConsultationNoteResponse,
    DiscrepancyResponse,
    EntryResponse,
    FactResponse,
    PatientCaseResponse,
    PatientVisitItem,
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
        required_attachment_kinds=hospital_config.required_attachment_kinds(),
        pending_attachment_kinds=case_repo.pending_attachment_kinds(db, case.id),
    )


def attachment_out(a: MedicalAttachment) -> AttachmentResponse:
    return AttachmentResponse(
        id=str(a.id), kind=a.kind, filename=a.filename, mime_type=a.mime_type, size_bytes=a.size_bytes,
        has_text=bool(a.extracted_text), extracted_text=a.extracted_text, uploaded_by=a.uploaded_by, created_at=a.created_at,
    )


def active_intake_out(db: Session, session: IntakeSession, case: PatientCase) -> ActiveIntakeResponse:
    messages = case_repo.messages(db, session.id)
    identity_complete = not case_repo.missing_identity_fields(db, case.id)
    if identity_complete and messages:
        messages = messages[1:]
    completed_turn = (
        db.query(AuditEvent)
        .filter(AuditEvent.case_id == case.id, AuditEvent.action == "intake.turn_processed")
        .order_by(AuditEvent.created_at.desc())
        .first()
    )
    base = session_out(db, session, case)
    return ActiveIntakeResponse(
        **base.model_dump(),
        identity_complete=identity_complete,
        intake_complete=bool(completed_turn and completed_turn.payload.get("intake_complete")),
        transcript=[
            TranscriptMessage(role=message.role, content=message.content, turn_index=message.turn_index)
            for message in messages
        ],
        attachments=[attachment_out(attachment) for attachment in case_repo.attachments(db, case.id)],
        skipped_attachment_kinds=sorted(case_repo.skipped_attachment_kinds(db, case.id)),
    )


def triage_out(db: Session, t: TriageResult | None) -> TriageResponse | None:
    if t is None:
        return None
    rule_ids = []
    for value in t.rule_ids or []:
        try:
            rule_ids.append(uuid.UUID(str(value)))
        except (TypeError, ValueError):
            continue
    rows = db.query(TriageRule).filter(TriageRule.id.in_(rule_ids)).all() if rule_ids else []
    by_id = {row.id: row for row in rows}
    rules = [by_id[rule_id] for rule_id in rule_ids if rule_id in by_id]
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
    # n.doctor_id is the verified hospital-system identity (an OpenEMR Practitioner UUID),
    # not a local hospital_config.yaml doctor id, so n.doctor_name (captured at write-time)
    # is the name to show; the YAML lookup is kept only as a fallback for a ConsultationNote
    # row written before doctor_name existed.
    doctor = hospital_config.doctor_by_id(n.doctor_id)
    display_name = n.doctor_name or (doctor["name"] if doctor else None)
    return ConsultationNoteResponse(
        id=str(n.id), doctor_id=n.doctor_id, doctor_name=display_name,
        consultation_mode=n.consultation_mode, notes=n.notes, prescription=n.prescription,
        follow_up_instructions=n.follow_up_instructions, created_at=n.created_at,
    )


def task_out(t: CareTask) -> CareTaskResponse:
    return CareTaskResponse(
        id=str(t.id), task_type=t.task_type, status=t.status, priority=t.priority, payload=t.payload or {},
        hms_reference=t.hms_reference, notes=t.notes, created_at=t.created_at,
    )


def discrepancy_out(d) -> DiscrepancyResponse:
    return DiscrepancyResponse(
        id=str(d.id), field_or_topic=d.field_or_topic, patient_stated=d.patient_stated, document_says=d.document_says,
        source_kind=d.source_kind, attachment_id=str(d.attachment_id) if d.attachment_id else None,
        severity=d.severity, requested_document_kind=d.requested_document_kind, generated_by=d.generated_by,
        created_at=d.created_at,
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
        required_attachment_kinds=hospital_config.required_attachment_kinds(),
        pending_attachment_kinds=case_repo.pending_attachment_kinds(db, case.id),
        triage=triage_out(db, case_repo.latest_triage(db, case.id)),
        routing=routing_out(case_repo.latest_routing(db, case.id)),
        discrepancies=[discrepancy_out(d) for d in case_repo.discrepancies(db, case.id)],
        prescreening_summary=summary_out(case_repo.summary(db, case.id, "prescreening")),
        review=review_out(case_repo.latest_review(db, case.id)),
        consultation_notes=[note_out(n) for n in case_repo.notes(db, case.id)],
        final_summary=summary_out(case_repo.summary(db, case.id, "final_visit")),
        care_tasks=[task_out(t) for t in case_repo.tasks(db, case.id)],
        created_at=case.created_at,
    )


def patient_case_detail(db: Session, case: PatientCase) -> PatientCaseResponse:
    session = case_repo.session_for(db, case)
    review = case_repo.latest_review(db, case.id)
    approved = review is not None and review.decision in {"approve", "edit"}
    final_summary = case_repo.summary(db, case.id, "final_visit") if session.status == "COMPLETED" else None
    notes = case_repo.notes(db, case.id) if final_summary else []
    tasks = case_repo.tasks(db, case.id) if final_summary else []
    return PatientCaseResponse(
        case_id=str(case.id),
        status=session.status,
        review_decision=review.decision if review else None,
        routing=routing_out(case_repo.latest_routing(db, case.id)) if approved else None,
        final_summary=final_summary.sections if final_summary else None,
        consultation_mode=notes[-1].consultation_mode if notes else None,
        appointment_reference=tasks[0].hms_reference if tasks else None,
        created_at=case.created_at,
    )


def patient_case_list(db: Session, cases: list[PatientCase]) -> list[PatientVisitItem]:
    if not cases:
        return []
    case_ids = [case.id for case in cases]
    sessions = {
        row.id: row
        for row in db.query(IntakeSession).filter(IntakeSession.id.in_([case.session_id for case in cases])).all()
    }
    routing = {
        row.case_id: row
        for row in (
            db.query(RoutingRecommendation)
            .filter(RoutingRecommendation.case_id.in_(case_ids))
            .order_by(RoutingRecommendation.case_id, RoutingRecommendation.created_at.desc())
            .distinct(RoutingRecommendation.case_id)
            .all()
        )
    }
    reviews = {
        row.case_id: row
        for row in (
            db.query(ClinicalReview)
            .filter(ClinicalReview.case_id.in_(case_ids))
            .order_by(ClinicalReview.case_id, ClinicalReview.created_at.desc())
            .distinct(ClinicalReview.case_id)
            .all()
        )
    }
    updated = dict(
        db.query(AuditEvent.case_id, func.max(AuditEvent.created_at))
        .filter(AuditEvent.case_id.in_(case_ids))
        .group_by(AuditEvent.case_id)
        .all()
    )
    items = []
    for case in cases:
        session = sessions[case.session_id]
        case_routing = routing.get(case.id)
        review = reviews.get(case.id)
        approved = review is not None and review.decision in {"approve", "edit"}
        items.append(
            PatientVisitItem(
                case_id=str(case.id),
                status=session.status,
                review_decision=review.decision if review else None,
                department_name=case_routing.department_name if case_routing and approved else None,
                doctor_name=case_routing.doctor_name if case_routing and approved else None,
                created_at=case.created_at,
                updated_at=updated.get(case.id),
            )
        )
    return items


def case_list(db: Session, cases: list[PatientCase] | None = None) -> list[CaseListItem]:
    items = []
    rows = cases if cases is not None else db.query(PatientCase).order_by(PatientCase.created_at.desc()).all()
    if not rows:
        return items
    case_ids = [case.id for case in rows]
    sessions = {
        row.id: row
        for row in db.query(IntakeSession).filter(IntakeSession.id.in_([case.session_id for case in rows])).all()
    }

    def latest(model):
        return {
            row.case_id: row
            for row in (
                db.query(model)
                .filter(model.case_id.in_(case_ids))
                .order_by(model.case_id, model.created_at.desc())
                .distinct(model.case_id)
                .all()
            )
        }

    triage = latest(TriageResult)
    routing = latest(RoutingRecommendation)
    reviews = latest(ClinicalReview)
    facts_by_case = defaultdict(list)
    for fact in (
        db.query(PatientFact)
        .filter(PatientFact.case_id.in_(case_ids))
        .order_by(PatientFact.case_id, PatientFact.source_turn, PatientFact.created_at)
        .all()
    ):
        facts_by_case[fact.case_id].append(fact)
    entries_by_case = defaultdict(list)
    for entry in (
        db.query(AllergyMedication)
        .filter(AllergyMedication.case_id.in_(case_ids))
        .order_by(AllergyMedication.case_id, AllergyMedication.source_turn, AllergyMedication.created_at)
        .all()
    ):
        entries_by_case[entry.case_id].append(entry)
    updated = dict(
        db.query(AuditEvent.case_id, func.max(AuditEvent.created_at))
        .filter(AuditEvent.case_id.in_(case_ids))
        .group_by(AuditEvent.case_id)
        .all()
    )
    required_fields = hospital_config.required_intake_fields()
    for case in rows:
        session = sessions.get(case.session_id)
        case_triage = triage.get(case.id)
        case_routing = routing.get(case.id)
        review = reviews.get(case.id)
        facts = facts_by_case[case.id]
        entries = entries_by_case[case.id]
        reason = next((fact.value for fact in facts if fact.kind == "reason_for_visit"), None)
        items.append(CaseListItem(
            case_id=str(case.id), session_id=str(case.session_id), status=session.status if session else "UNKNOWN",
            priority=case_triage.priority if case_triage else None,
            department_id=case_routing.department_id if case_routing else None,
            department_name=case_routing.department_name if case_routing else None,
            doctor_id=case_routing.doctor_id if case_routing else None,
            doctor_name=case_routing.doctor_name if case_routing else None,
            chief_complaint=reason, demographics=case.demographics or {}, hms_patient_id=case.hms_patient_id,
            review_decision=review.decision if review else None,
            missing_count=len(intake_fields.missing_fields(required_fields, facts, entries)),
            created_at=case.created_at, updated_at=updated.get(case.id),
        ))
    return items
