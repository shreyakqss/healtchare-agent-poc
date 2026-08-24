from __future__ import annotations

from datetime import datetime
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
    kind: str
    filename: str
    mime_type: str
    size_bytes: int
    has_text: bool
    extracted_text: str | None
    uploaded_by: str
    created_at: datetime


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
    created_at: datetime
    updated_at: datetime | None


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
    triage: TriageResponse | None
    routing: RoutingResponse | None
    prescreening_summary: SummaryResponse | None
    review: ReviewResponse | None
    consultation_notes: list[ConsultationNoteResponse]
    final_summary: SummaryResponse | None
    care_tasks: list[CareTaskResponse]
    created_at: datetime


class ClinicOverview(BaseModel):
    total: int
    by_status: dict[str, int]
    by_priority: dict[str, int]
    by_department: dict[str, int]
    awaiting_review: int
    completed_today: int