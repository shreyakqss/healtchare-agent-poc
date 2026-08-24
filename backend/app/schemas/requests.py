from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class StartSessionRequest(BaseModel):
    # Link to a known HMS patient; their record pre-fills demographics and history.
    mrn: str | None = None
    channel: Literal["web", "kiosk", "staff"] = "web"
    demographics: dict[str, Any] = Field(default_factory=dict)


class QuickStartRequest(BaseModel):
    """Demo shortcut: fill a whole intake instantly instead of typing it. See
    app/services/quick_start.py for the fixed set of keys this accepts."""

    key: str


class ConsentRequest(BaseModel):
    granted: bool


class MessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=4000)


class ReviewRequest(BaseModel):
    decision: Literal["approve", "edit", "reject"]
    reviewer_id: str = Field(min_length=1, max_length=64)
    reviewer_role: str = "clinician"
    edits: dict[str, Any] = Field(default_factory=dict)
    comment: str | None = None


class ConsultationNoteRequest(BaseModel):
    doctor_id: str
    consultation_mode: Literal["in_person", "virtual"] = "in_person"
    notes: str = Field(min_length=1)
    prescription: str | None = None
    follow_up_instructions: str | None = None


class NewHospitalRequest(BaseModel):
    hospital_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,62}$")
    yaml: str | None = None


class HospitalYamlRequest(BaseModel):
    yaml: str