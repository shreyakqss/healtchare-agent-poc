"""The doctor's "Past patients" view: every patient with a visit that is over, one row per patient
(by hospital record, MRN), newest visit first, with that patient's visits under it.

A visit is over when the case was completed or rejected, or its booked time has passed (a
default time the patient never confirmed does not count). Built
from the clinic-scoped case list (`serializers.case_list`), so it sees exactly the cases the
clinician may already open - nothing new is stored and no access rule changes."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.schemas.responses import CaseListItem, PastPatientItem, PastVisitItem

CLOSED = {"COMPLETED", "REJECTED"}
# Enough history for a clinic POC; the newest cases are scanned first.
MAX_CASES_SCANNED = 1000


def is_past(item: CaseListItem, now: datetime) -> bool:
    return item.status in CLOSED or (
        item.appointment_booked and item.appointment_start is not None and item.appointment_start <= now
    )


def _visit_at(item: CaseListItem, now: datetime) -> datetime:
    """The booked time once it has come; a case closed before it (rejected) dates from its close."""
    if item.appointment_start is not None and item.appointment_start <= now:
        return item.appointment_start
    return item.updated_at or item.created_at


def _matches(item: CaseListItem, needle: str) -> bool:
    haystack = " ".join(filter(None, (
        str(item.demographics.get("name") or ""), item.hms_patient_id, item.chief_complaint, item.doctor_name,
    ))).lower()
    return needle in haystack


def group(
    items: list[CaseListItem], *, now: datetime | None = None, doctor_id: str | None = None,
    query: str | None = None, days: int | None = None,
) -> list[PastPatientItem]:
    """`doctor_id` keeps only that doctor's visits ("mine"); `query` matches name, MRN, complaint
    or doctor; `days` keeps patients whose last visit falls within that many days."""
    now = now or datetime.now(UTC)
    needle = (query or "").strip().lower()
    since = now - timedelta(days=days) if days else None
    visits: dict[str, list[CaseListItem]] = {}
    for item in items:
        if item.emergency or not is_past(item, now):
            continue
        if doctor_id and item.doctor_id != doctor_id:
            continue
        visits.setdefault(item.hms_patient_id or item.case_id, []).append(item)

    patients: list[PastPatientItem] = []
    for key, rows in visits.items():
        rows.sort(key=lambda r: _visit_at(r, now), reverse=True)
        last = rows[0]
        if since and _visit_at(last, now) < since:
            continue
        if needle and not any(_matches(r, needle) for r in rows):
            continue
        patients.append(PastPatientItem(
            patient_key=key, hms_patient_id=last.hms_patient_id,
            name=last.demographics.get("name"), age=last.demographics.get("age"), sex=last.demographics.get("sex"),
            last_visit_at=_visit_at(last, now), visit_count=len(rows),
            visits=[PastVisitItem(
                case_id=r.case_id, visit_at=_visit_at(r, now), status=r.status, review_decision=r.review_decision,
                chief_complaint=r.chief_complaint, department_name=r.department_name, doctor_id=r.doctor_id, doctor_name=r.doctor_name,
            ) for r in rows],
        ))
    patients.sort(key=lambda p: p.last_visit_at, reverse=True)
    return patients
