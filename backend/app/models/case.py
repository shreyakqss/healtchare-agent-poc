import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PatientCase(Base):
    __tablename__ = "patient_cases"

    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("intake_sessions.id", ondelete="CASCADE"), index=True, unique=True
    )
    # Name/age/sex aren't cached here - app.services.case_repo.demographics() derives them.
    # HMS medical record number when intake was started against a known patient.
    hms_patient_id: Mapped[str | None] = mapped_column(String(64), index=True)
    hospital_id: Mapped[str] = mapped_column(String(64), index=True)
    specialty_hint: Mapped[str | None] = mapped_column(String(128))
    # When a red-flag (emergency) triage rule first matched, during intake or pre-screening. From
    # then on the patient is told to seek emergency care instead of being offered a booking.
    emergency_flagged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # The patient's confirmed appointment on the doctor's HMS calendar (OpenEMR's pc_eid), set
    # when the patient confirms a time and replaced when they change it. No clinician approves it.
    hms_appointment_id: Mapped[str | None] = mapped_column(String(64))
    # "new" (a new problem) or "follow_up" (about the problem of `follow_up_of`, one of this
    # patient's own completed visits): the follow-up is routed to that visit's department with
    # its doctor offered first, and intake and the doctor see what was diagnosed and prescribed.
    visit_type: Mapped[str] = mapped_column(String(16), default="new", server_default="new")
    follow_up_of: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("patient_cases.id", ondelete="SET NULL"), nullable=True, index=True
    )