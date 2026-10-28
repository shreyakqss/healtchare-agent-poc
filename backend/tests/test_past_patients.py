"""services/past_patients.group: which visits count as past, grouping per patient, filters. Pure."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.schemas.responses import CaseListItem
from app.services import past_patients

NOW = datetime(2026, 10, 28, 12, 0, tzinfo=UTC)


def item(case_id: str, *, mrn: str | None = "100", status: str = "COMPLETED", start: datetime | None = None,
         doctor: str = "dr-a", name: str = "Suresh Patel", complaint: str = "fever", emergency: bool = False,
         booked: bool = True) -> CaseListItem:
    return CaseListItem(
        case_id=case_id, session_id="s", status=status, priority="low", department_id="gm", department_name="General Medicine",
        doctor_id=doctor, doctor_name=doctor.upper(), chief_complaint=complaint, demographics={"name": name, "age": "34", "sex": "male"},
        hms_patient_id=mrn, review_decision=None, missing_count=0, emergency=emergency,
        appointment_start=start, appointment_booked=booked, created_at=NOW - timedelta(days=40), updated_at=None,
    )


def test_groups_visits_per_patient_newest_first_and_skips_upcoming_and_emergencies():
    rows = [
        item("old", start=NOW - timedelta(days=30)),
        item("new", status="APPROVED", start=NOW - timedelta(hours=2)),  # booked time passed
        item("future", status="APPROVED", start=NOW + timedelta(days=1)),
        item("default", mrn="400", status="NEEDS_REVIEW", start=NOW - timedelta(days=2), booked=False),  # never confirmed
        item("other", mrn="200", name="Neha Joshi", status="REJECTED", start=NOW + timedelta(days=3)),
        item("er", mrn="300", status="NEEDS_REVIEW", emergency=True),
    ]
    out = past_patients.group(rows, now=NOW)
    assert [p.patient_key for p in out] == ["100", "200"]
    assert [v.case_id for v in out[0].visits] == ["new", "old"] and out[0].visit_count == 2


def test_filters_by_doctor_search_and_recency():
    rows = [
        item("a", start=NOW - timedelta(days=5), doctor="dr-a"),
        item("b", mrn="200", name="Neha Joshi", complaint="palpitations", start=NOW - timedelta(days=200), doctor="dr-b"),
    ]
    assert [p.patient_key for p in past_patients.group(rows, now=NOW, doctor_id="dr-b")] == ["200"]
    assert [p.patient_key for p in past_patients.group(rows, now=NOW, query="PALPIT")] == ["200"]
    assert [p.patient_key for p in past_patients.group(rows, now=NOW, query="100")] == ["100"]  # MRN
    assert [p.patient_key for p in past_patients.group(rows, now=NOW, days=30)] == ["100"]
