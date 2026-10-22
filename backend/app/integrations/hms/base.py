from __future__ import annotations

from datetime import datetime
from typing import Protocol

from app.integrations.hms.schemas import (
    AppointmentRequest,
    AppointmentRequestResult,
    HMSDocument,
    HMSFacility,
    HMSPatient,
    HMSPractitioner,
    HMSSlot,
    HMSStatus,
    HMSWeeklyHours,
    PatientRegistration,
    VerifiedIdentity,
)


class HMSClient(Protocol):
    """What the application needs from a hospital management system.

    Read side: patient registry, practitioner roster, open slots.
    Write side: appointment *requests* only - drafts the HMS staff confirm.
    """

    def status(self) -> HMSStatus: ...

    def get_facility(self) -> HMSFacility | None:
        """The clinic this CareFlow instance serves, as the hospital system records it.
        `None` when the hospital system has no facility on file or is unreachable - the
        clinic config's own `hospital:` block is then the fallback."""
        ...

    def search_patients(self, query: str, limit: int = 10) -> list[HMSPatient]: ...
    def get_patient(self, mrn: str) -> HMSPatient | None: ...
    def register_patient(self, existing_mrn: str | None, registration: PatientRegistration) -> HMSPatient: ...
    def sync_reviewed_intake(self, mrn: str, payload: dict) -> None: ...
    def list_documents(self, mrn: str, limit: int = 20) -> list[HMSDocument]:
        """Past documents on file for the patient (e.g. prior visit summaries pushed via
        `push_document`, or records already in the HMS). Read-only, shown to the patient/
        clinician for context - never fed to `triage_engine`.
        """
        ...
    def get_document_content(self, mrn: str, reference: str) -> tuple[bytes, str, str]: ...
    def list_practitioners(self, limit: int = 100) -> list[HMSPractitioner]: ...
    def available_slots(self, department_id: str, practitioner_id: str | None = None, limit: int = 5) -> list[HMSSlot]: ...
    def office_hours(self, practitioner_id: str) -> list[HMSWeeklyHours]:
        """The practitioner's weekly consulting hours as the HMS publishes them, clinic-local.
        `[]` when it publishes none."""
        ...
    def book_appointment(self, mrn: str, practitioner_id: str, start: datetime, end: datetime, note: str) -> str:
        """Put the patient's confirmed appointment on the practitioner's calendar. Returns the
        HMS's id for it, which `cancel_appointment` takes."""
        ...
    def cancel_appointment(self, reference: str) -> None: ...
    def request_appointment(self, request: AppointmentRequest) -> AppointmentRequestResult: ...
    def list_requests(self, limit: int = 100) -> list[AppointmentRequestResult]: ...

    def push_document(self, mrn: str, title: str, content: bytes, content_type: str = "text/plain") -> str:
        """Push a clinician-approved artifact (visit summary, consultation note) to the HMS.

        `content` is the raw bytes to store (already-encoded text, or an uploaded file's raw
        bytes) - callers are responsible for encoding. Returns a reference string for the
        created record. Never used to push raw, unreviewed AI output - callers are expected to
        gate this behind the same human-review checks that gate `/consultation-notes` and
        `/finalize`.
        """
        ...

    def verify_credentials(self, username: str, password: str) -> VerifiedIdentity | None:
        """Validate a clinician's real HMS login, to attribute a review/consultation action
        to a real identity.

        Not a session/auth system - a one-shot credential check performed per action. Never
        raises; returns `None` on any failure (bad credentials, HMS unreachable, malformed
        response).
        """
        ...
