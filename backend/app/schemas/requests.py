from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StartSessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ConsentRequest(BaseModel):
    granted: bool


class IdentityFormRequest(BaseModel):
    """Step 1 of intake: who the patient is. Submitted at once, before the clinical
    conversation starts. Field names match app/domain/intake_fields.py::FIELD_SATISFIED_BY."""

    # Every required field carries min_length=1 so a blank one is a 422 from the request
    # schema, before the hospital system is asked to store it.
    name: str = Field(min_length=1, max_length=200)
    birth_date: date
    gender: str = Field(min_length=1, max_length=40)
    phone: str | None = None
    email: str | None = None
    address_line1: str = Field(min_length=1, max_length=200)
    address_line2: str | None = None
    city: str = Field(min_length=1, max_length=100)
    state: str = Field(min_length=1, max_length=100)
    postal_code: str = Field(min_length=1, max_length=20)
    country: str = Field(min_length=1, max_length=100)
    contact_preference: str = Field(min_length=1, max_length=40)

    @field_validator("birth_date")
    @classmethod
    def birth_date_must_not_be_future(cls, value: date) -> date:
        if value > datetime.now(UTC).date():
            raise ValueError("Date of birth cannot be in the future.")
        return value


class MessageRequest(BaseModel):
    """Step 2 of intake: one turn of the clinical conversation (reason for visit,
    symptoms, duration, history, medications, allergies)."""

    content: str = Field(min_length=1, max_length=4000)


class AttachmentSkipRequest(BaseModel):
    kind: str
    reason: str | None = None


class ReviewRequest(BaseModel):
    decision: Literal["approve", "edit", "reject"]
    reviewer_username: str = Field(min_length=1, max_length=64)
    reviewer_password: str = Field(min_length=1)
    edits: dict[str, Any] = Field(default_factory=dict)
    comment: str | None = None


class ConsultationNoteRequest(BaseModel):
    doctor_username: str = Field(min_length=1, max_length=64)
    doctor_password: str = Field(min_length=1)
    consultation_mode: Literal["in_person", "virtual"] = "in_person"
    notes: str = Field(min_length=1)
    prescription: str | None = None
    follow_up_instructions: str | None = None
    tests_ordered: str | None = None
    referral_notes: str | None = None
    # The doctor's own final-draft report to the patient. Optional: when blank, the model
    # drafts the patient-facing summary from these notes at finalize time, same as before.
    patient_report: str | None = None


class AppointmentSlotRequest(BaseModel):
    slot_id: str = Field(min_length=1, max_length=64)


class DoctorAssistantTurn(BaseModel):
    role: Literal["doctor", "assistant"]
    content: str = Field(min_length=1, max_length=4000)


class DoctorAssistantRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    doctor_context: str = Field(min_length=1, max_length=300)
    transcript: list[DoctorAssistantTurn] = Field(default_factory=list, max_length=20)


class FinalizeRequest(BaseModel):
    """Same clinician-credential-verification pattern as ReviewRequest/ConsultationNoteRequest -
    finalize triggers HMS writes (request_appointment, push_document) and previously ran with
    zero identity check."""

    finalizer_username: str = Field(min_length=1, max_length=64)
    finalizer_password: str = Field(min_length=1)


class NewHospitalRequest(BaseModel):
    hospital_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,62}$")
    yaml: str | None = None


class HospitalYamlRequest(BaseModel):
    yaml: str


class NewDoctorRequest(BaseModel):
    """Admin > Doctors > Add doctor. The hospital is never a field: it is the admin's own."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str = Field(default="Dr.", max_length=30)
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", max_length=254)
    phone: str = Field(default="", max_length=30)
    username: str = Field(min_length=3, max_length=32)
    password: str = Field(min_length=1, max_length=128)
    npi: str = Field(min_length=1, max_length=10)
    department_id: str = Field(min_length=1, max_length=100)
    specialty_code: str = Field(min_length=1, max_length=20)
    licence: str = Field(default="", max_length=60)
    days: list[str] = Field(default_factory=list)
    ranges: list[tuple[str, str]] = Field(default_factory=list)
    start_date: date
    weeks: int = Field(ge=1, le=26)

    @field_validator("username")
    @classmethod
    def username_lowercase(cls, value: str) -> str:
        return value.lower()


class ExtendHoursRequest(BaseModel):
    weeks: int = Field(ge=1, le=26)


class ChangeHoursRequest(BaseModel):
    """Admin > Doctors > Edit hours: from `start_date` on, these hours replace what was published."""

    model_config = ConfigDict(extra="forbid")

    days: list[str] = Field(default_factory=list)
    ranges: list[tuple[str, str]] = Field(default_factory=list)
    start_date: date
    weeks: int = Field(ge=1, le=26)
