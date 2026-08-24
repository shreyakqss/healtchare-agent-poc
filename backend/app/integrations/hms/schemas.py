"""Contracts for the HMS (hospital management system) boundary.

Shaped after FHIR resources (Patient, Practitioner, Slot, Appointment) but kept
flat - the POC never talks to a real FHIR server.
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field


class HMSPatient(BaseModel):
    mrn: str = Field(description="Medical record number - the HMS identifier")
    name: str
    age: int
    sex: str
    phone: str | None = None
    conditions: list[str] = Field(default_factory=list)
    medications: list[str] = Field(default_factory=list)
    allergies: list[str] = Field(default_factory=list)
    last_visit: date | None = None


class HMSPractitioner(BaseModel):
    id: str
    name: str
    department_id: str
    working_days: list[str] = Field(default_factory=list)


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