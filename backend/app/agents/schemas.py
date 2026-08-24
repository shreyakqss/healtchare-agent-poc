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


class VisitSummary(BaseModel):
    visit_reason: str
    consultation_overview: str
    doctor_notes_summary: str
    follow_up_instructions: list[str] = Field(default_factory=list)
    patient_friendly_summary: str = Field(description="Two or three plain sentences the patient can read.")