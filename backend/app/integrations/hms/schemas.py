"""Contracts for the HMS (hospital management system) boundary.

Shaped after FHIR resources (Patient, Practitioner, Slot, Appointment) but kept flat -
the application never handles a raw FHIR resource, only these.
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field


class HMSAddress(BaseModel):
    """A postal address as the hospital system holds it. Every field is optional: an EMR
    record is often partial, and the intake form is what completes it."""

    line1: str = ""
    line2: str | None = None
    city: str = ""
    state: str = ""
    postal_code: str = ""
    country: str = ""


class HMSFacility(BaseModel):
    """The clinic itself, as the hospital system records it. CareFlow shows this rather than
    keeping a second copy of the clinic's name and address in its own config."""

    id: str
    name: str
    phone: str | None = None
    email: str | None = None
    website: str | None = None
    address: HMSAddress | None = None


class HMSPatient(BaseModel):
    mrn: str = Field(description="Medical record number - the HMS identifier")
    name: str
    age: int
    sex: str
    # Date of birth as recorded in the HMS. `age` is derived from it for display; the date
    # itself is what pre-fills the intake identity form.
    birth_date: date | None = None
    phone: str | None = None
    email: str | None = None
    address: HMSAddress | None = None
    # How the patient asked to be contacted last time ("phone" | "email"), as the hospital
    # system recorded it. Pre-fills the intake form; the patient still confirms it per visit.
    contact_preference: str | None = None
    conditions: list[str] = Field(default_factory=list)
    medications: list[str] = Field(default_factory=list)
    allergies: list[str] = Field(default_factory=list)
    last_visit: date | None = None


class HMSDocument(BaseModel):
    """A document on file for a patient in the HMS.

    Read-only, shown to the patient/clinician for context (prior visit summaries pushed
    via `push_document`, or records already in the HMS). Never fed to `triage_engine`.
    """

    reference: str
    title: str
    content_type: str = "text/plain"
    created: datetime | None = None


class PatientRegistration(BaseModel):
    """Demographics collected by CareFlow and written to the HMS patient record."""

    name: str
    birth_date: date
    gender: str
    phone: str | None = None
    email: str | None = None
    address_line1: str
    address_line2: str | None = None
    city: str
    state: str
    postal_code: str
    country: str
    contact_preference: str


class HMSPractitioner(BaseModel):
    id: str
    name: str
    department_id: str
    specialty: str | None = None
    working_days: list[str] = Field(default_factory=list)
    # The clinician's *login* name, which is what the hospital system authenticates. `id` is
    # the practitioner record's id and is never accepted as a credential, so offering it as
    # one only produces a 401. `None` when the HMS exposes no login for this practitioner.
    username: str | None = None


class HMSSlot(BaseModel):
    id: str
    practitioner_id: str
    department_id: str
    start: datetime
    end: datetime


class AppointmentRequest(BaseModel):
    case_id: str
    patient_mrn: str | None
    patient_name: str
    department_id: str
    practitioner_id: str | None
    appointment_type_id: str
    priority: str
    preferred_slot_id: str | None = None
    reason: str


class AppointmentRequestResult(BaseModel):
    reference: str
    status: str = "requested"  # never "booked" - the POC does not confirm appointments
    slot: HMSSlot | None = None


class HMSStatus(BaseModel):
    provider: str
    connected: bool
    patients: int
    practitioners: int
    pending_requests: int


class VerifiedIdentity(BaseModel):
    """A clinician identity verified against the HMS's own login, for a single action.

    Not a session or token - a one-shot credential check used to attribute a review or
    consultation to a real identity rather than a free-text name.
    """

    id: str
    name: str
