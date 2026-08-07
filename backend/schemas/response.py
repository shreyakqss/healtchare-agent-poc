"""Outbound API contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class SessionResponse(BaseModel):
    session_id: str
    case_id: str
    status: str
    consent_status: str


class MessageResponse(BaseModel):
    session_id: str
    case_id: str
    turn_index: int
    next_question: str
    missing_fields: list[str]
    intake_complete: bool
    transcript: list[dict[str, str]]


class AttachmentResponse(BaseModel):
    id: str
    kind: str
    filename: str
    mime_type: str
    size_bytes: int
    has_extracted_text: bool
    # Images are stored and displayed only; never interpreted.
    interpreted: bool = False
    created_at: datetime


class FactResponse(BaseModel):
    id: str
    kind: str
    value: str
    source_turn: int
    confidence: float


class AllergyMedicationResponse(BaseModel):
    id: str
    kind: str
    name: str
    reaction_or_dose: str | None
    source_turn: int


class TriageResponse(BaseModel):
    priority: str
    rule_ids: list[Any]
    rule_codes: list[str]
    warnings: list[Any]
    evidence: list[Any]


class RoutingResponse(BaseModel):
    specialty: str
    appointment_type: str
    rationale: str
    department_id: str | None
    doctor_id: str | None
    doctor_name: str | None


class SummaryResponse(BaseModel):
    id: str
    kind: str
    sections: dict[str, Any]
    evidence: list[Any]
    missing_information: list[Any]
    created_at: datetime


class ReviewResponse(BaseModel):
    id: str
    decision: str
    reviewer_role: str
    edits: dict[str, Any]
    created_at: datetime


class ConsultationNoteResponse(BaseModel):
    id: str
    doctor_id: str
    notes: str
    follow_up_instructions: str | None
    created_at: datetime


class CaseDetailResponse(BaseModel):
    case_id: str
    session_id: str
    status: str
    consent_status: str
    demographics: dict[str, Any]
    transcript: list[dict[str, str]]
    facts: list[FactResponse]
    allergies_medications: list[AllergyMedicationResponse]
    attachments: list[AttachmentResponse]
    triage: TriageResponse | None
    routing: RoutingResponse | None
    prescreening_summary: SummaryResponse | None
    review: ReviewResponse | None
    consultation_notes: list[ConsultationNoteResponse]
    final_summary: SummaryResponse | None
    missing_fields: list[str]


class CaseListItem(BaseModel):
    case_id: str
    session_id: str
    status: str
    priority: str | None
    department: str | None
    doctor_name: str | None
    chief_complaint: str | None
    created_at: datetime
    updated_at: datetime | None


class AuditEventResponse(BaseModel):
    id: str
    actor: str
    action: str
    payload: dict[str, Any]
    created_at: datetime
