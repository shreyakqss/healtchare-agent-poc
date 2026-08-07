import uuid

from sqlalchemy import ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from models.database import Base


class MedicalAttachment(Base):
    """An uploaded medical document or image.

    Stored and displayed only. `extracted_text` is populated for document
    formats; image pixels are never interpreted and an attachment can never
    change a triage priority on its own.
    """

    __tablename__ = "medical_attachments"

    case_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("patient_cases.id", ondelete="CASCADE"), index=True
    )
    # radiology | pathology | lab_report | prescription | referral | other
    kind: Mapped[str] = mapped_column(String(32))
    filename: Mapped[str] = mapped_column(String(255))
    mime_type: Mapped[str] = mapped_column(String(128))
    size_bytes: Mapped[int] = mapped_column(Integer)
    storage_uri: Mapped[str] = mapped_column(Text)
    # None for images — text extraction only applies to document formats
    extracted_text: Mapped[str | None] = mapped_column(Text)
    source_turn: Mapped[int] = mapped_column(Integer, default=0)
