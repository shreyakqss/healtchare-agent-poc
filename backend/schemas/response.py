"""Outbound API contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

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
    # Which required field the question above is for. Recorded on the message
    # row either way; returned here so the client can offer one-tap answers for
    # it without having to infer the field from the wording.
    asks_field: str | None = None


class AnswerOptionsResponse(BaseModel):
    """One-tap answers offered beside a question. Never required to proceed."""

    field: str | None
    options: list[str]
    #: "static" for a fixed list, "llm" for generated, "none" when there are
    #: none — shown in the operations view so a degraded model is visible.
    source: str
    #: Option -> what to type after tapping it ("Phone" -> "Your phone number").
    #: Only the contact question uses this; the tapped option and what is typed
    #: still leave as one ordinary patient message.
    follow_ups: dict[str, str] = {}


class TurnEvent(BaseModel):
    """One frame of an intake turn in progress.

    Deliberately one flat model rather than a discriminated union: it crosses
    the wire as SSE `data:` lines, and the four shapes are small enough that a
    `type` switch on the client beats four schemas to keep in step.

        token    a chunk of the assistant's reply, for the screen
        segment  a speakable phrase, for text-to-speech
        done     the canonical turn — this, not the chunks, is what was stored
        error    the turn failed; `detail` is patient-safe
    """

    type: Literal["token", "segment", "done", "error"]
    text: str | None = None
    index: int | None = None
    response: MessageResponse | None = None
    status: int | None = None
    detail: str | None = None


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
    # The queue shows who is waiting, so the fixture demographics ride along
    # rather than making the dashboard fetch every case detail to find them.
    demographics: dict[str, Any] = {}
    created_at: datetime
    updated_at: datetime | None


class AuditEventResponse(BaseModel):
    id: str
    actor: str
    action: str
    payload: dict[str, Any]
    created_at: datetime
