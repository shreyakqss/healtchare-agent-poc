"""Inbound API contracts."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class StartSessionRequest(BaseModel):
    demographics: dict[str, Any] = Field(
        default_factory=dict,
        description="Synthetic demographic fixture. No real patient data.",
    )


class ConsentRequest(BaseModel):
    granted: bool


class MessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=4000)
    # How the patient produced this turn. Recorded on the audit event and
    # nothing else — a spoken turn and a typed turn are processed identically,
    # so this must never be branched on.
    channel: Literal["text", "voice"] = "text"


class SuggestionRequest(BaseModel):
    """Ask for one-tap answers to the question just asked."""

    question: str = Field(min_length=1, max_length=2000)
    #: The required field the question is for, as returned on the turn. Decides
    #: whether the answers are a fixed list or are generated.
    field: str | None = None


class ReviewRequest(BaseModel):
    decision: Literal["approve", "edit", "reject"]
    reviewer_role: str = Field(default="clinician", max_length=64)
    edits: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Reviewer corrections, stored separately from the original "
            "patient-reported facts."
        ),
    )


class ConsultationNoteRequest(BaseModel):
    doctor_id: str = Field(max_length=64)
    notes: str = Field(min_length=1)
    follow_up_instructions: str | None = None
    # "in_person" | "virtual". Defaulted rather than required so existing
    # callers keep working; nothing in the workflow branches on it.
    consultation_mode: Literal["in_person", "virtual"] = "in_person"
    prescription: str | None = None
    attachment_ids: list[str] = Field(default_factory=list)
