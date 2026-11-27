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
    "negative",
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


class FocusedQuestion(BaseModel):
    done: bool = Field(description="True when the doctor already has enough history for this complaint.")
    question: str = Field(default="", description="The next question to the patient; empty when done.")
    topic: str = Field(default="", description="What it asks about, e.g. 'cough', 'tonsil swelling', 'dehydration'.")


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


class MedicationSuggestion(BaseModel):
    name: str = Field(description="Generic drug name, e.g. 'Phenoxymethylpenicillin'.")
    dose: str = Field(description="Typical adult dose for this patient, e.g. '500 mg'.")
    route: str = Field(description="e.g. 'oral'.")
    frequency: str = Field(description="e.g. 'four times a day'.")
    duration: str = Field(description="e.g. '5 to 10 days', or 'as needed'.")
    purpose: str = Field(description="Why: 'first-line antibiotic', 'fever and pain relief', 'rehydration'.")
    caution: str = Field(default="", description="Allergy, interaction, age or pregnancy caution for THIS patient; empty if none.")


class DiagnosisSuggestion(BaseModel):
    condition: str = Field(description="The condition's clinical name.")
    likelihood: Literal["high", "medium", "low"]
    supporting: list[str] = Field(default_factory=list, description="Findings in the case that point to it.")
    against: list[str] = Field(default_factory=list, description="Findings in the case that argue against it.")
    tests: list[str] = Field(default_factory=list, description="Investigations that would confirm or exclude it.")
    management: list[str] = Field(default_factory=list, description="Non-drug management and advice if confirmed.")
    medications: list[MedicationSuggestion] = Field(
        default_factory=list,
        description="Guideline first-line regimen if confirmed, already adjusted for this patient's allergies and medicines.",
    )
    allergy_check: str = Field(
        default="",
        description="How the regimen accounts for the recorded allergies and current medicines, in one line.",
    )


class AIDiagnosis(BaseModel):
    """Decision support for the treating doctor. Never shown to the patient unless the doctor
    writes it into the consultation themselves."""

    differentials: list[DiagnosisSuggestion] = Field(
        default_factory=list, description="Most likely first; only genuinely plausible ones (often one to three, never more than five)."
    )
    red_flags: list[str] = Field(
        default_factory=list, description="Serious conditions that must be excluded, with the reason."
    )
    missing_information: list[str] = Field(
        default_factory=list, description="Questions or findings that would change the differential."
    )
    safety_alerts: list[str] = Field(
        default_factory=list,
        description="Allergy cross-reactions, drug interactions or contraindications the doctor must see before prescribing.",
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


ReportSection = Literal[
    "complaints", "history", "past_history", "allergies", "medications", "examination",
    "diagnosis", "investigations", "prescription", "advice", "follow_up", "referral",
]


class ReportDraft(BaseModel):
    """The OPD consultation record (SOAP / ABDM OP consultation shape), written the way a doctor
    charts: terse clinical lines, never narrative or commentary. No examination: only the doctor
    examined the patient."""

    complaints: str = Field(description="Presenting complaints with duration, one per line, e.g. 'Fever x 3 days'.")
    history: str = Field(description="History of presenting illness: 2 to 4 short clinical lines, including pertinent negatives.")
    past_history: str = Field(description="Relevant past medical/surgical history, one per line; 'Nil significant' if none.")
    allergies: str = Field(description="Drug and other allergies with reaction, one per line; 'NKDA' if none.")
    medications: str = Field(description="Current medicines the patient takes, one per line; 'Nil' if none.")
    diagnosis: str = Field(description="Diagnosis name(s) only, one per line, optionally with ICD-10 code in brackets.")
    investigations: str = Field(description="Test names only, one per line; empty if none.")
    prescription: str = Field(description="Rx, one medicine per line: form, generic name, strength, dose schedule, duration, instructions.")
    advice: str = Field(description="Advice for the patient, short plain-language lines.")
    follow_up: str = Field(description="When to review and when to return earlier, one line.")
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


class DepartmentPick(BaseModel):
    department_id: str = Field(description="One department id from the clinic's list, exactly as given.")
    reason: str = Field(description="One short clinical phrase for the doctor, e.g. 'Fever with cough, likely chest infection'.")
    facts_used: list[str] = Field(
        default_factory=list, description="The patient facts the choice rests on, copied word for word from the list."
    )


class FileRead(BaseModel):
    """The AI's read of one uploaded image or scanned document, for the treating doctor only."""

    what_it_is: str = Field(description="What the file shows, e.g. 'Chest X-ray, PA view' or 'Scanned CBC report'.")
    findings: list[str] = Field(
        default_factory=list,
        description="Short lines on what is visible, or the key values read from a report with units and flags.",
    )
    impression: str = Field(description="One line on what the findings may suggest; empty when nothing stands out.")
    limitations: str = Field(description="One line on image quality or what cannot be judged; empty when none.")
