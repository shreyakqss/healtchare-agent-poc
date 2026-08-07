"""Intake Agent — opens a session and records consent.

No LLM. Creating a case and capturing consent are record-keeping steps, and
consent in particular must be a plain auditable write.
"""
import uuid
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from models import AuditEvent, IntakeSession, PatientCase


def start_session(db: Session, demographics: dict | None = None) -> tuple[IntakeSession, PatientCase]:
    """Create the session and its patient case. Status stays CREATED until consent."""
    session = IntakeSession(status="CREATED", consent_status="PENDING")
    db.add(session)
    db.flush()

    case = PatientCase(
        session_id=session.id,
        demographics_fixture=demographics or {},
    )
    db.add(case)
    db.flush()

    db.add(
        AuditEvent(
            case_id=case.id,
            actor="patient",
            action="intake.session_started",
            payload={"session_id": str(session.id)},
        )
    )
    db.commit()
    return session, case

def record_consent(
    db: Session, session: IntakeSession, case_id: uuid.UUID, granted: bool
) -> IntakeSession:
    """Capture the consent decision. Nothing else may run until this is GRANTED."""
    session.consent_status = "GRANTED" if granted else "DECLINED"

    if granted:
        session.status = "INGESTING"
        session.started_at = datetime.now(timezone.utc)
    else:
        session.status = "REJECTED"
        session.completed_at = datetime.now(timezone.utc)

    db.add(
        AuditEvent(
            case_id=case_id,
            actor="patient",
            action="intake.consent_recorded",
            payload={"consent_status": session.consent_status},
        )
    )
    db.commit()
    db.refresh(session)
    return session
