from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class SessionResponse(BaseModel):
    session_id: str
    case_id: str
    status: str
    consent_status: str
    demographics: dict[str, Any] = Field(default_factory=dict)
    hms_linked: bool = False
    missing_fields: list[str] = Field(default_factory=list)
    captured_fields: dict[str, list[str]] = Field(default_factory=dict)
    required_attachment_kinds: list[str] = Field(default_factory=list)
    pending_attachment_kinds: list[str] = Field(default_factory=list)
    past_attachments: list[AttachmentResponse] = Field(default_factory=list)


class TranscriptMessage(BaseModel):
    role: str
    content: str
    turn_index: int


class MessageResponse(BaseModel):
    session_id: str
    case_id: str
    turn_index: int
    reply: str
    asks_field: str | None
    missing_fields: list[str]
    intake_complete: bool
    transcript: list[TranscriptMessage]
    captured_fields: dict[str, list[str]] = Field(default_factory=dict)


class AttachmentSkipResponse(BaseModel):
    ok: bool


class TurnEvent(BaseModel):
    """One SSE frame. `token` is transport; `done` is the record."""

    type: Literal["token", "done", "error"]
    text: str | None = None
    response: MessageResponse | None = None
    status: int | None = None
    detail: str | None = None


class FactResponse(BaseModel):
    id: str
    kind: str
    value: str
    source: str
    source_turn: int
    confidence: float


class EntryResponse(BaseModel):
    id: str
    kind: str
    name: str
    reaction_or_dose: str | None
    source: str
    source_turn: int


class AttachmentResponse(BaseModel):
    id: str
    case_id: str
    kind: str
    filename: str
    mime_type: str
    size_bytes: int
    has_text: bool
    extracted_text: str | None
    uploaded_by: str
    created_at: datetime


class ActiveIntakeResponse(SessionResponse):
    identity_complete: bool
    intake_complete: bool
    transcript: list[TranscriptMessage] = Field(default_factory=list)
    attachments: list[AttachmentResponse] = Field(default_factory=list)
    skipped_attachment_kinds: list[str] = Field(default_factory=list)


class LinkedPatientRecord(BaseModel):
    """Prefill for the identity form when this account is linked to an existing OpenEMR
    patient (Keycloak `hms_patient_id`). The patient still confirms every field before it is
    written back - this never submits on their behalf."""

    name: str
    birth_date: date | None = None
    gender: str
    phone: str | None = None
    email: str | None = None
    address_line1: str | None = None
    address_line2: str | None = None
    city: str | None = None
    state: str | None = None
    postal_code: str | None = None
    country: str | None = None
    contact_preference: str | None = None


class TriageResponse(BaseModel):
    priority: str
    rule_codes: list[str]
    rules: list[dict[str, Any]]
    warnings: list[dict[str, Any]]
    evidence: list[dict[str, Any]]
    created_at: datetime


class SlotResponse(BaseModel):
    id: str
    practitioner_id: str
    department_id: str
    start: datetime
    end: datetime
    # Another patient holds this time: shown greyed out in the patient's picker, not pickable.
    taken: bool = False


class DoctorAssistantResponse(BaseModel):
    reply: str


class RoutingResponse(BaseModel):
    department_id: str
    department_name: str
    doctor_id: str | None
    doctor_name: str | None
    appointment_type_id: str
    appointment_type_label: str
    rationale: str
    matched_keywords: list[str]
    suggested_slot: SlotResponse | None
    slot_options: list[SlotResponse]
    selected_slot_id: str | None


class PatientRoutingResponse(BaseModel):
    department_id: str
    department_name: str
    doctor_id: str | None
    doctor_name: str | None
    appointment_type_id: str
    appointment_type_label: str
    suggested_slot: SlotResponse | None
    slot_options: list[SlotResponse]
    selected_slot_id: str | None


class SummaryResponse(BaseModel):
    id: str
    kind: str
    sections: dict[str, Any]
    evidence: list[dict[str, Any]]
    missing_information: list[str]
    generated_by: str
    created_at: datetime


class ReviewResponse(BaseModel):
    id: str
    decision: str
    reviewer_id: str
    reviewer_role: str
    edits: dict[str, Any]
    comment: str | None
    created_at: datetime


class ConsultationNoteResponse(BaseModel):
    id: str
    doctor_id: str
    doctor_name: str | None
    consultation_mode: str
    notes: str
    prescription: str | None
    follow_up_instructions: str | None
    tests_ordered: str | None
    referral_notes: str | None
    patient_report: str | None
    created_at: datetime


class CareTaskResponse(BaseModel):
    id: str
    task_type: str
    status: str
    priority: str
    payload: dict[str, Any]
    hms_reference: str | None
    notes: str | None
    created_at: datetime


class AuditEventResponse(BaseModel):
    id: str
    actor: str
    action: str
    payload: dict[str, Any]
    created_at: datetime


class DiscrepancyResponse(BaseModel):
    id: str
    field_or_topic: str
    patient_stated: str
    document_says: str
    source_kind: str
    attachment_id: str | None
    severity: str
    requested_document_kind: str | None
    generated_by: str
    created_at: datetime


class RosterDoctor(BaseModel):
    id: str
    name: str
    department_id: str
    specialty: str | None = None
    working_days: list[str] = Field(default_factory=list)
    # The clinician's hospital-system login, for pre-filling the credential prompt. `id` is a
    # practitioner record id, which the hospital system never accepts as a username.
    username: str | None = None


class RosterResponse(BaseModel):
    """Doctors a case can be routed to. `source` says whether at least one department is
    served by live HMS practitioners ("hms") or the whole list came from the YAML ("config")."""

    source: Literal["hms", "config"]
    doctors: list[RosterDoctor]


class CaseListItem(BaseModel):
    case_id: str
    session_id: str
    status: str
    priority: str | None
    department_id: str | None
    department_name: str | None
    doctor_id: str | None
    doctor_name: str | None
    chief_complaint: str | None
    demographics: dict[str, Any]
    hms_patient_id: str | None
    review_decision: str | None
    missing_count: int
    appointment_start: datetime | None
    created_at: datetime
    updated_at: datetime | None


class PatientVisitItem(BaseModel):
    case_id: str
    status: str
    review_decision: str | None
    department_name: str | None
    doctor_name: str | None
    created_at: datetime
    updated_at: datetime | None


class PatientCaseResponse(BaseModel):
    case_id: str
    status: str
    review_decision: str | None
    routing: PatientRoutingResponse | None
    final_summary: dict[str, Any] | None
    consultation_mode: str | None
    appointment_reference: str | None
    created_at: datetime


class CaseDetailResponse(BaseModel):
    case_id: str
    session_id: str
    status: str
    consent_status: str
    channel: str
    hospital_id: str
    demographics: dict[str, Any]
    hms_patient_id: str | None
    transcript: list[TranscriptMessage]
    facts: list[FactResponse]
    allergies_medications: list[EntryResponse]
    attachments: list[AttachmentResponse]
    missing_fields: list[str]
    required_attachment_kinds: list[str] = Field(default_factory=list)
    pending_attachment_kinds: list[str] = Field(default_factory=list)
    triage: TriageResponse | None
    routing: RoutingResponse | None
    discrepancies: list[DiscrepancyResponse] = Field(default_factory=list)
    prescreening_summary: SummaryResponse | None
    review: ReviewResponse | None
    consultation_notes: list[ConsultationNoteResponse]
    final_summary: SummaryResponse | None
    care_tasks: list[CareTaskResponse]
    created_at: datetime
