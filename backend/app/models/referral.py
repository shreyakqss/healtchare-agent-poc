import uuid

from sqlalchemy import ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Referral(Base):
    """One doctor sending a patient on to another department (services/referral_service).

    Signed by the referring doctor with their HMS identity. It opens a linked visit
    (`case_id`, `PatientCase.visit_type="referral"`) in the target department, already booked
    with that department's doctor; the patient sees it under My visits and may change the time
    like any visit they booked. The referring visit (`source_case_id`) is untouched - its
    signed notes, reports and intake are shown to the receiving doctor from there.

    Where the referral stands is read from the linked visit (booked, seen, released), so
    nothing here goes stale; only the referring doctor's words are stored.
    """

    __tablename__ = "referrals"

    source_case_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("patient_cases.id", ondelete="CASCADE"), index=True
    )
    case_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("patient_cases.id", ondelete="CASCADE"), index=True, unique=True
    )
    from_doctor_id: Mapped[str] = mapped_column(String(64))
    from_doctor_name: Mapped[str] = mapped_column(String(128))
    from_department_name: Mapped[str | None] = mapped_column(String(128))
    to_department_id: Mapped[str] = mapped_column(String(64))
    to_department_name: Mapped[str] = mapped_column(String(128))
    # The doctor asked for by name, if any; who actually holds the booking is on the routing.
    to_doctor_id: Mapped[str | None] = mapped_column(String(64))
    to_doctor_name: Mapped[str | None] = mapped_column(String(128))
    reason: Mapped[str] = mapped_column(Text)
    # What the referring doctor wants answered ("please evaluate exertional chest pain").
    question: Mapped[str | None] = mapped_column(Text)
    # How soon the patient should be seen - shown to the receiving doctor and sent to the HMS as
    # its risk level. Never a triage priority: those come from triage_engine alone.
    urgency: Mapped[str] = mapped_column(String(16), default="routine")
    # The HMS's referral record (OpenEMR LBTref transaction), when it could be written.
    hms_reference: Mapped[str | None] = mapped_column(String(128))
