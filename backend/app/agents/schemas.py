"""Typed outputs for every LLM call. No numeric constraints - strict JSON schema mode rejects them."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

QuestionResponse = Literal["answered", "denied", "declined", "not_answered"]
QuestionScope = Literal[
    "personal_record",
    "clinic",
    "general_health",
    "restricted_healthcare",
    "urgent_safety",
    "out_of_scope",
]

FactKind = Literal[
    "reason_for_visit", "symptom", "duration", "history", "contact_preference", "name", "age", "gender",
]


class ExtractedFact(BaseModel):
    kind: FactKind
    value: str = Field(description="The patient's own words for this one item, under 15 words.")
    normalized: str = Field(
        default="",
        description="The clinic term this wording means, copied exactly from the list supplied; empty when none fits.",
    )
    confidence: float = Field(default=1.0)


class ExtractedEntry(BaseModel):
    kind: Literal["allergy", "medication"]
    name: str
    reaction_or_dose: str = ""


class ExtractionResult(BaseModel):
    facts: list[ExtractedFact] = Field(default_factory=list)
    allergies_medications: list[ExtractedEntry] = Field(default_factory=list)
    current_question_response: QuestionResponse = Field(
        description="Whether the message answers the clinic's current intake question.",
    )
    patient_question: str | None = Field(
        default=None,
        description="A self-contained question or request for the assistant, even when the message also answers intake.",
    )
    question_scope: QuestionScope | None = Field(
        default=None,
        description="The capability needed to answer patient_question; null when there is no patient question.",
    )
    health_topic: str | None = Field(
        default=None,
        description="A short identifier-free lookup topic for general_health; null for every other scope.",
    )


class PatientAnswerReview(BaseModel):
    decision: Literal["allow", "block"] = Field(
        description="Whether the answer is grounded and stays within the patient assistant's safety boundary."
    )


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


class MedicationCandidatesResult(BaseModel):
    medications: list[str] = Field(
        default_factory=list, description="Medication names found in the document, patient's own product/brand names where given."
    )


class DiagnosisSuggestion(BaseModel):
    condition: str = Field(description="The condition's clinical name.")
    likelihood: Literal["high", "medium", "low"]
    supporting: list[str] = Field(default_factory=list, description="Findings in the case that point to it.")
    against: list[str] = Field(default_factory=list, description="Findings in the case that argue against it.")
    tests: list[str] = Field(default_factory=list, description="Investigations that would confirm or exclude it.")
    management: list[str] = Field(default_factory=list, description="Treatment approaches to consider if confirmed.")


class AIDiagnosis(BaseModel):
    """Decision support for the treating doctor. Never shown to the patient unless the doctor
    writes it into the consultation themselves."""

    differentials: list[DiagnosisSuggestion] = Field(
        default_factory=list, description="Most likely first, at most five."
    )
    red_flags: list[str] = Field(
        default_factory=list, description="Serious conditions that must be excluded, with the reason."
    )
    missing_information: list[str] = Field(
        default_factory=list, description="Questions or findings that would change the differential."
    )
    reasoning: str = Field(description="Two to four sentences on how the differential was reached.")


class ProposedDiagnosis(BaseModel):
    condition: str = Field(description="A medical condition the text proposes for this patient, by its clinical name.")
    likelihood: Literal["high", "medium", "low"] = Field(description="How strongly the text favours it.")
    supporting: list[str] = Field(default_factory=list, description="The text's own reasons for it, short.")


class ProposedDiagnoses(BaseModel):
    conditions: list[ProposedDiagnosis] = Field(
        default_factory=list,
        description="Empty when the text proposes no diagnosis (advice, dosing, test lists, questions).",
    )


ReportSection = Literal["history", "examination", "diagnosis", "investigations", "prescription", "advice", "referral"]


class ReportDraft(BaseModel):
    """The consultation report template (ABDM OP consultation shape). No examination: only the
    doctor examined the patient."""

    history: str = Field(description="Presenting complaint and relevant history, clinical prose.")
    diagnosis: str = Field(description="Provisional diagnosis, one per line, from the accepted diagnoses only.")
    investigations: str = Field(description="Investigations advised, one per line.")
    prescription: str = Field(
        description="One medicine per line: form, name, strength, dose, frequency, route, duration, instructions."
    )
    advice: str = Field(description="Advice and follow-up for the patient, plain language, one point per line.")
    referral: str = Field(description="Notes for other doctors; empty when there is nothing to hand over.")


class ReportEdit(BaseModel):
    section: ReportSection
    text: str = Field(description="The complete new text of the section, not a fragment.")
    reason: str = Field(description="One short line on what changed.")


class ReportEditProposal(BaseModel):
    reply: str = Field(description="One or two sentences to the doctor about the proposed change.")
    edits: list[ReportEdit] = Field(default_factory=list)


class VisitSummary(BaseModel):
    visit_reason: str
    consultation_overview: str
    doctor_notes_summary: str
    follow_up_instructions: list[str] = Field(default_factory=list)
    patient_friendly_summary: str = Field(description="Two or three plain sentences the patient can read.")
