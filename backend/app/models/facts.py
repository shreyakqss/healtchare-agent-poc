import uuid

from sqlalchemy import Boolean, Float, ForeignKey, Integer, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# Provenance of a row. Patient statements and HMS record imports stay
# distinguishable; reviewer corrections never land here (see ClinicalReview.edits).
SOURCE_PATIENT = "patient"
SOURCE_HMS = "hms"
NO_TURN = -1


class PatientFact(Base):
    __tablename__ = "patient_facts"

    case_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("patient_cases.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(64), index=True)
    value: Mapped[str] = mapped_column(Text)
    # The clinic term this wording means, so a paraphrase still reaches the rule written for
    # it. A label beside the patient's words, never a replacement for them.
    normalized: Mapped[str] = mapped_column(String(255), default="")
    source: Mapped[str] = mapped_column(String(16), default=SOURCE_PATIENT)
    source_turn: Mapped[int] = mapped_column(Integer, default=NO_TURN)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)


class AllergyMedication(Base):
    __tablename__ = "allergy_medications"

    case_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("patient_cases.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(32))  # allergy | medication
    name: Mapped[str] = mapped_column(String(255))
    reaction_or_dose: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(16), default=SOURCE_PATIENT)
    source_turn: Mapped[int] = mapped_column(Integer, default=NO_TURN)


class MedicalAttachment(Base):
    """Uploaded document or image. Never fed to triage_engine - it evaluates rules,
    not documents. `extracted_text` is shown to the clinician as-is and may also be
    read by a discrepancy-check agent to raise clinician-facing flags (not yet added);
    neither path lets an attachment change a priority."""

    __tablename__ = "medical_attachments"

    case_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("patient_cases.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(32))
    filename: Mapped[str] = mapped_column(String(255))
    mime_type: Mapped[str] = mapped_column(String(128))
    size_bytes: Mapped[int] = mapped_column(Integer)
    storage_uri: Mapped[str] = mapped_column(Text)
    extracted_text: Mapped[str | None] = mapped_column(Text)  # None for images
    # Medication names found on a prescription document by medication_extractor.py. Candidates
    # only - never written as AllergyMedication rows directly; they are surfaced as a confirm
    # question, and only the patient's chat reply creates real entries.
    extracted_medications: Mapped[list[str] | None] = mapped_column(JSON)
    # Set once this attachment's candidates have been put to the patient as a confirm question,
    # so a second upload's new candidates still get asked even after an earlier one was answered.
    medication_candidates_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    uploaded_by: Mapped[str] = mapped_column(String(64), default="patient")
    # Display/audit field only - set when the raw file is best-effort forwarded to the
    # linked HMS record via push_document(). Never consumed by triage_engine.
    hms_reference: Mapped[str | None] = mapped_column(String(128), nullable=True)