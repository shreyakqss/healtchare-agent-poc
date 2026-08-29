"""Typed outputs for every LLM call. No numeric constraints - strict JSON schema mode rejects them."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

FactKind = Literal[
    "reason_for_visit", "symptom", "duration", "history", "contact_preference", "name", "age", "gender",
]


class ExtractedFact(BaseModel):
    kind: FactKind
    value: str = Field(description="The patient's own words for this one item, under 15 words.")
    confidence: float = Field(default=1.0)


class ExtractedEntry(BaseModel):
    kind: Literal["allergy", "medication"]
    name: str
    reaction_or_dose: str = ""


class ExtractionResult(BaseModel):
    facts: list[ExtractedFact] = Field(default_factory=list)
    allergies_medications: list[ExtractedEntry] = Field(default_factory=list)


class PrescreeningSummary(BaseModel):
    chief_complaint: str
    reported_symptoms: list[str] = Field(default_factory=list)
    relevant_history: list[str] = Field(default_factory=list)
    medications: list[str] = Field(default_factory=list)
    allergies: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    context_for_clinician: str = Field(
        description="Neutral summary of what the patient stated. No diagnosis, no treatment, no urgency."
    )


class Discrepancy(BaseModel):
    field_or_topic: str = Field(description="Short label for what mismatches, e.g. 'medications' or 'symptom duration'.")
    patient_stated: str = Field(description="What the patient said, in their own words.")
    document_or_hms_says: str = Field(description="What the document or HMS record says instead.")
    source_kind: Literal["document", "hms"]
    attachment_id: str | None = Field(default=None, description="Id of the MedicalAttachment this came from, if source_kind is 'document'.")
    severity: Literal["info", "review"]
    requested_document_kind: str | None = Field(
        default=None, description="An attachment kind worth requesting from the patient to resolve this, if any."
    )


class DiscrepancyResult(BaseModel):
    discrepancies: list[Discrepancy] = Field(default_factory=list)


class VisitSummary(BaseModel):
    visit_reason: str
    consultation_overview: str
    doctor_notes_summary: str
    follow_up_instructions: list[str] = Field(default_factory=list)
    patient_friendly_summary: str = Field(description="Two or three plain sentences the patient can read.")