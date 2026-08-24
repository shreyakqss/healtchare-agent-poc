"""In-memory HMS backed by a YAML registry and the active hospital roster.

Deterministic on purpose: slots are generated from each practitioner's working
days so a demo is repeatable, and appointment requests live only in memory.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, time, timedelta
from pathlib import Path

import yaml

from app.integrations.hms.schemas import (
    AppointmentRequest,
    AppointmentRequestResult,
    HMSPatient,
    HMSPractitioner,
    HMSSlot,
    HMSStatus,
)
from app.services import hospital_config

_WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


class MockHMS:
    provider = "mock"

    def __init__(self, fixture: Path):
        self._fixture = fixture
        self._patients: dict[str, HMSPatient] = {}
        self._requests: list[AppointmentRequestResult] = []
        self.reload()

    def reload(self) -> None:
        raw = yaml.safe_load(self._fixture.read_text(encoding="utf-8")) if self._fixture.exists() else {}
        self._patients = {p["mrn"]: HMSPatient(**p) for p in (raw or {}).get("patients", [])}

    # --- read side -------------------------------------------------------

    def status(self) -> HMSStatus:
        return HMSStatus(
            provider=self.provider,
            connected=True,
            patients=len(self._patients),
            practitioners=len(self.list_practitioners()),
            pending_requests=len(self._requests),
        )

    def search_patients(self, query: str, limit: int = 10) -> list[HMSPatient]:
        q = query.strip().lower()
        if not q:
            return list(self._patients.values())[:limit]
        hits = [p for p in self._patients.values() if q in p.mrn.lower() or q in p.name.lower()]
        return hits[:limit]

    def get_patient(self, mrn: str) -> HMSPatient | None:
        return self._patients.get(mrn)

    def list_practitioners(self) -> list[HMSPractitioner]:
        return [
            HMSPractitioner(
                id=d["id"], name=d["name"], department_id=d["department_id"],
                working_days=d.get("working_days", []),
            )
            for d in hospital_config.doctors()
        ]

    def available_slots(self, department_id: str, practitioner_id: str | None = None, limit: int = 5) -> list[HMSSlot]:
        slots: list[HMSSlot] = []
        roster = [p for p in self.list_practitioners() if p.department_id == department_id]
        if practitioner_id:
            roster = [p for p in roster if p.id == practitioner_id]
        taken = {r.slot.id for r in self._requests if r.slot}
        day = datetime.now(UTC).date() + timedelta(days=1)
        for _ in range(14):
            weekday = _WEEKDAYS[day.weekday()]
            for p in roster:
                if weekday not in p.working_days:
                    continue
                for hour, minute in ((9, 0), (9, 30), (10, 0), (11, 0), (14, 0), (15, 30)):
                    start = datetime.combine(day, time(hour, minute), tzinfo=UTC)
                    slot = HMSSlot(
                        id=f"{p.id}-{start:%Y%m%d%H%M}", practitioner_id=p.id,
                        department_id=department_id, start=start, end=start + timedelta(minutes=30),
                    )
                    if slot.id not in taken:
                        slots.append(slot)
                    if len(slots) >= limit:
                        return slots
            day += timedelta(days=1)
        return slots

    # --- write side (drafts only) ----------------------------------------

    def request_appointment(self, request: AppointmentRequest) -> AppointmentRequestResult:
        slot = None
        if request.preferred_slot_id:
            slot = next(
                (s for s in self.available_slots(request.department_id, request.practitioner_id, limit=50)
                 if s.id == request.preferred_slot_id),
                None,
            )
        if slot is None:
            candidates = self.available_slots(request.department_id, request.practitioner_id, limit=1)
            slot = candidates[0] if candidates else None
        result = AppointmentRequestResult(reference=f"REQ-{uuid.uuid4().hex[:8].upper()}", slot=slot)
        self._requests.append(result)
        return result

    def list_requests(self) -> list[AppointmentRequestResult]:
        return list(self._requests)