from __future__ import annotations

from typing import Protocol

from app.integrations.hms.schemas import (
    AppointmentRequest,
    AppointmentRequestResult,
    HMSPatient,
    HMSPractitioner,
    HMSSlot,
    HMSStatus,
)


class HMSClient(Protocol):
    """What the application needs from a hospital management system.

    Read side: patient registry, practitioner roster, open slots.
    Write side: appointment *requests* only - drafts the HMS staff confirm.
    """

    def status(self) -> HMSStatus: ...
    def search_patients(self, query: str, limit: int = 10) -> list[HMSPatient]: ...
    def get_patient(self, mrn: str) -> HMSPatient | None: ...
    def list_practitioners(self) -> list[HMSPractitioner]: ...
    def available_slots(self, department_id: str, practitioner_id: str | None = None, limit: int = 5) -> list[HMSSlot]: ...
    def request_appointment(self, request: AppointmentRequest) -> AppointmentRequestResult: ...
    def list_requests(self) -> list[AppointmentRequestResult]: ...