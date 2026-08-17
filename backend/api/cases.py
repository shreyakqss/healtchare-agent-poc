"""Patient cases: profile, attachments, pre-screening, consultation, finalisation."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from agents.human_review import is_approved, latest_review
from agents.question_planner import missing_fields
from models import (
    AllergyMedication,
    AuditEvent,
    ClinicalSummary,
    ConsultationNote,
    IntakeMessage,
    IntakeSession,
    MedicalAttachment,
    PatientCase,
    PatientFact,
    RoutingRecommendation,
    TriageResult,
    TriageRule,
    get_db,
)
from schemas.request import ConsultationNoteRequest
from schemas.response import (
    AllergyMedicationResponse,
    AttachmentResponse,
    CaseDetailResponse,
    CaseListItem,
    ConsultationNoteResponse,
    FactResponse,
    ReviewResponse,
    RoutingResponse,
    SummaryResponse,
    TriageResponse,
)
from services import extraction, hospital_config
from workflow.graph import finalize_graph, prescreen_graph, run_config

router = APIRouter(prefix="/cases", tags=["cases"])


# --- serialisation ---------------------------------------------------------


def _case_or_404(db: Session, case_id: uuid.UUID) -> PatientCase:
    case = db.get(PatientCase, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Patient case not found.")
    return case


def _attachment_out(a: MedicalAttachment) -> AttachmentResponse:
    return AttachmentResponse(
        id=str(a.id),
        kind=a.kind,
        filename=a.filename,
        mime_type=a.mime_type,
        size_bytes=a.size_bytes,
        has_extracted_text=bool(a.extracted_text),
        interpreted=False,
        created_at=a.created_at,
    )


def _summary_out(s: ClinicalSummary | None) -> SummaryResponse | None:
    if s is None:
        return None
    return SummaryResponse(
        id=str(s.id),
        kind=s.kind,
        sections=s.sections or {},
        evidence=s.evidence or [],
        missing_information=s.missing_information or [],
        created_at=s.created_at,
    )


def _latest_triage(db: Session, case_id) -> TriageResult | None:
    return (
        db.query(TriageResult)
        .filter(TriageResult.case_id == case_id)
        .order_by(TriageResult.created_at.desc())
        .first()
    )


def _latest_routing(db: Session, case_id) -> RoutingRecommendation | None:
    return (
        db.query(RoutingRecommendation)
        .filter(RoutingRecommendation.case_id == case_id)
        .order_by(RoutingRecommendation.created_at.desc())
        .first()
    )


def _summary(db: Session, case_id, kind: str) -> ClinicalSummary | None:
    return (
        db.query(ClinicalSummary)
        .filter(ClinicalSummary.case_id == case_id, ClinicalSummary.kind == kind)
        .order_by(ClinicalSummary.created_at.desc())
        .first()
    )


def _rule_codes(db: Session, triage: TriageResult | None) -> list[str]:
    """Resolve stored rule ids back to the human-readable codes clinicians see."""
    if triage is None or not triage.rule_ids:
        return []
    codes: list[str] = []
    for raw in triage.rule_ids:
        try:
            rule = db.get(TriageRule, uuid.UUID(str(raw)))
        except (ValueError, TypeError):
            rule = None
        codes.append(rule.code if rule else str(raw))
    return codes


# --- endpoints -------------------------------------------------------------


@router.get("", response_model=list[CaseListItem])
def list_cases(db: Session = Depends(get_db)):
    """Admin dashboard feed."""
    cases = db.query(PatientCase).order_by(PatientCase.created_at.desc()).all()

    items: list[CaseListItem] = []
    for case in cases:
        session = db.get(IntakeSession, case.session_id)
        triage = _latest_triage(db, case.id)
        routing = _latest_routing(db, case.id)
        doctor = hospital_config.doctor_by_id(routing.doctor_id) if routing else None
        reason = (
            db.query(PatientFact)
            .filter(
                PatientFact.case_id == case.id,
                PatientFact.kind == "reason_for_visit",
            )
            .first()
        )
        last_event = (
            db.query(AuditEvent)
            .filter(AuditEvent.case_id == case.id)
            .order_by(AuditEvent.created_at.desc())
            .first()
        )

        items.append(
            CaseListItem(
                case_id=str(case.id),
                session_id=str(case.session_id),
                status=session.status if session else "UNKNOWN",
                priority=triage.priority if triage else None,
                department=routing.specialty if routing else None,
                doctor_name=doctor["name"] if doctor else None,
                chief_complaint=reason.value if reason else None,
                demographics=case.demographics_fixture or {},
                created_at=case.created_at,
                updated_at=last_event.created_at if last_event else None,
            )
        )
    return items


@router.get("/{case_id}", response_model=CaseDetailResponse)
def get_case(case_id: uuid.UUID, db: Session = Depends(get_db)):
    case = _case_or_404(db, case_id)
    session = db.get(IntakeSession, case.session_id)

    triage = _latest_triage(db, case.id)
    routing = _latest_routing(db, case.id)
    doctor = hospital_config.doctor_by_id(routing.doctor_id) if routing else None
    review = latest_review(db, case.id)

    messages = (
        db.query(IntakeMessage)
        .filter(IntakeMessage.session_id == case.session_id)
        .order_by(IntakeMessage.turn_index)
        .all()
    )
    facts = db.query(PatientFact).filter(PatientFact.case_id == case.id).all()
    entries = (
        db.query(AllergyMedication)
        .filter(AllergyMedication.case_id == case.id)
        .all()
    )
    attachments = (
        db.query(MedicalAttachment)
        .filter(MedicalAttachment.case_id == case.id)
        .order_by(MedicalAttachment.created_at)
        .all()
    )
    notes = (
        db.query(ConsultationNote)
        .filter(ConsultationNote.case_id == case.id)
        .order_by(ConsultationNote.created_at)
        .all()
    )

    return CaseDetailResponse(
        case_id=str(case.id),
        session_id=str(case.session_id),
        status=session.status if session else "UNKNOWN",
        consent_status=session.consent_status if session else "UNKNOWN",
        demographics=case.demographics_fixture or {},
        transcript=[{"role": m.role, "content": m.content} for m in messages],
        facts=[
            FactResponse(
                id=str(f.id),
                kind=f.kind,
                value=f.value,
                source_turn=f.source_turn,
                confidence=f.confidence,
            )
            for f in facts
        ],
        allergies_medications=[
            AllergyMedicationResponse(
                id=str(e.id),
                kind=e.kind,
                name=e.name,
                reaction_or_dose=e.reaction_or_dose,
                source_turn=e.source_turn,
            )
            for e in entries
        ],
        attachments=[_attachment_out(a) for a in attachments],
        triage=(
            TriageResponse(
                priority=triage.priority,
                rule_ids=triage.rule_ids or [],
                rule_codes=_rule_codes(db, triage),
                warnings=triage.warnings or [],
                evidence=triage.evidence or [],
            )
            if triage
            else None
        ),
        routing=(
            RoutingResponse(
                specialty=routing.specialty,
                appointment_type=routing.appointment_type,
                rationale=routing.rationale,
                department_id=routing.department_id,
                doctor_id=routing.doctor_id,
                doctor_name=doctor["name"] if doctor else None,
            )
            if routing
            else None
        ),
        prescreening_summary=_summary_out(_summary(db, case.id, "prescreening")),
        review=(
            ReviewResponse(
                id=str(review.id),
                decision=review.decision,
                reviewer_role=review.reviewer_role,
                edits=review.edits or {},
                created_at=review.created_at,
            )
            if review
            else None
        ),
        consultation_notes=[
            ConsultationNoteResponse(
                id=str(n.id),
                doctor_id=n.doctor_id,
                notes=n.notes,
                follow_up_instructions=n.follow_up_instructions,
                consultation_mode=n.consultation_mode,
                prescription=n.prescription,
                created_at=n.created_at,
            )
            for n in notes
        ],
        final_summary=_summary_out(_summary(db, case.id, "final_visit")),
        missing_fields=missing_fields(db, case.id),
    )


@router.post("/{case_id}/attachments", response_model=AttachmentResponse, status_code=201)
async def upload_attachment(
    case_id: uuid.UUID,
    file: UploadFile = File(...),
    kind: str = Form("other"),
    db: Session = Depends(get_db),
):
    """Store a medical document or image against the case.

    Documents get their text extracted; images are stored and displayed only.
    Nothing uploaded here can influence a triage priority.
    """
    case = _case_or_404(db, case_id)
    content = await file.read()

    try:
        stored = extraction.store(case.id, file.filename or "upload", content, kind)
    except extraction.UploadRejected as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    turn_index = (
        db.query(IntakeMessage).filter(IntakeMessage.session_id == case.session_id).count()
    )

    attachment = MedicalAttachment(
        case_id=case.id,
        kind=kind,
        filename=stored.filename,
        mime_type=stored.mime_type,
        size_bytes=stored.size_bytes,
        storage_uri=stored.storage_uri,
        extracted_text=stored.extracted_text,
        source_turn=turn_index,
    )
    db.add(attachment)
    db.add(
        AuditEvent(
            case_id=case.id,
            actor="patient",
            action="attachment.uploaded",
            payload={
                "kind": kind,
                "filename": stored.filename,
                "size_bytes": stored.size_bytes,
                "text_extracted": bool(stored.extracted_text),
                "interpreted": False,
            },
        )
    )
    db.commit()
    db.refresh(attachment)
    return _attachment_out(attachment)


@router.get("/{case_id}/attachments", response_model=list[AttachmentResponse])
def list_attachments(case_id: uuid.UUID, db: Session = Depends(get_db)):
    _case_or_404(db, case_id)
    attachments = (
        db.query(MedicalAttachment)
        .filter(MedicalAttachment.case_id == case_id)
        .order_by(MedicalAttachment.created_at)
        .all()
    )
    return [_attachment_out(a) for a in attachments]


@router.get("/{case_id}/attachments/{attachment_id}/file")
def download_attachment(
    case_id: uuid.UUID, attachment_id: uuid.UUID, db: Session = Depends(get_db)
):
    attachment = db.get(MedicalAttachment, attachment_id)
    if attachment is None or attachment.case_id != case_id:
        raise HTTPException(status_code=404, detail="Attachment not found.")

    path = extraction.absolute_path(attachment.storage_uri)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Stored file is missing.")
    return FileResponse(path, media_type=attachment.mime_type, filename=attachment.filename)


@router.post("/{case_id}/prescreen", response_model=CaseDetailResponse)
async def run_prescreening(case_id: uuid.UUID, db: Session = Depends(get_db)):
    """Rule-based triage, routing, and the clinician summary. Ends at NEEDS_REVIEW."""
    case = _case_or_404(db, case_id)
    session = db.get(IntakeSession, case.session_id)

    if session is None or session.consent_status != "GRANTED":
        raise HTTPException(
            status_code=403, detail="Consent must be granted before pre-screening."
        )

    await prescreen_graph.ainvoke(
        {"session_id": str(case.session_id), "case_id": str(case.id)},
        config=run_config(db),
    )
    return get_case(case_id, db)


@router.post(
    "/{case_id}/consultation-notes",
    response_model=ConsultationNoteResponse,
    status_code=201,
)
def add_consultation_note(
    case_id: uuid.UUID,
    payload: ConsultationNoteRequest,
    db: Session = Depends(get_db),
):
    case = _case_or_404(db, case_id)

    if not is_approved(db, case.id):
        raise HTTPException(
            status_code=409,
            detail="A clinician must review the case before consultation notes are recorded.",
        )

    note = ConsultationNote(
        case_id=case.id,
        doctor_id=payload.doctor_id,
        notes=payload.notes,
        follow_up_instructions=payload.follow_up_instructions,
        consultation_mode=payload.consultation_mode,
        prescription=payload.prescription,
        attachment_ids=payload.attachment_ids,
    )
    db.add(note)
    db.add(
        AuditEvent(
            case_id=case.id,
            actor=f"doctor:{payload.doctor_id}",
            action="consultation.notes_recorded",
            payload={
                "has_follow_up": bool(payload.follow_up_instructions),
                "has_prescription": bool(payload.prescription),
                "consultation_mode": payload.consultation_mode,
            },
        )
    )
    db.commit()
    db.refresh(note)

    return ConsultationNoteResponse(
        id=str(note.id),
        doctor_id=note.doctor_id,
        notes=note.notes,
        follow_up_instructions=note.follow_up_instructions,
        consultation_mode=note.consultation_mode,
        prescription=note.prescription,
        created_at=note.created_at,
    )


@router.post("/{case_id}/finalize", response_model=CaseDetailResponse)
async def finalize_case(case_id: uuid.UUID, db: Session = Depends(get_db)):
    """Generate the final visit summary and a draft care task.

    Hard gate: no patient-facing output is released before a clinician approved.
    """
    case = _case_or_404(db, case_id)

    if not is_approved(db, case.id):
        raise HTTPException(
            status_code=409,
            detail=(
                "This case has not been approved by a clinician. No visit summary "
                "can be released before human review."
            ),
        )

    has_notes = (
        db.query(ConsultationNote).filter(ConsultationNote.case_id == case.id).count()
    )
    if not has_notes:
        raise HTTPException(
            status_code=409,
            detail="Record the consultation notes before finalising the visit.",
        )

    await finalize_graph.ainvoke(
        {"session_id": str(case.session_id), "case_id": str(case.id)},
        config=run_config(db),
    )
    return get_case(case_id, db)
