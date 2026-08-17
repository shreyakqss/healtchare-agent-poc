import uuid
from typing import Any

from sqlalchemy import ForeignKey, String, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from models.database import Base


class ConsultationNote(Base):
    """The doctor's own notes after seeing the patient.

    Authored by a clinician, never by an agent — the final visit summary
    reads these but must not overwrite them.
    """

    __tablename__ = "consultation_notes"

    case_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("patient_cases.id", ondelete="CASCADE"), index=True
    )
    doctor_id: Mapped[str] = mapped_column(String(64))
    notes: Mapped[str] = mapped_column(Text)
    follow_up_instructions: Mapped[str | None] = mapped_column(Text)
    # How the consultation happened: "in_person" | "virtual". Recorded because
    # it is part of the visit record a patient is shown, not because anything
    # branches on it — the workflow is identical either way.
    consultation_mode: Mapped[str] = mapped_column(String(16), default="in_person")
    # What the doctor prescribed, in their own words. Kept apart from `notes`
    # so the patient's copy can show it as a prescription rather than burying
    # it in a paragraph. Authored by the clinician; no agent may write here.
    prescription: Mapped[str | None] = mapped_column(Text)
    # attachment ids uploaded by the doctor during consultation
    attachment_ids: Mapped[list[Any]] = mapped_column(JSONB, default=list)
