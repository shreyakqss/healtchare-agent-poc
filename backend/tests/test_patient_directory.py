"""services/patient_directory.build: one row per MRN, newest first, and never a clinical field. Pure."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.schemas.responses import CaseListItem
from app.services import patient_directory

NOW = datetime(2026, 10, 29, 9, 0, tzinfo=UTC)
CLINICAL = {"chief_complaint", "priority", "review_decision", "missing_count", "emergency", "case_id", "session_id"}


def item(mrn: str | None, start: datetime | None, name: str = "Suresh Patel") -> CaseListItem:
    return CaseListItem(
        case_id="c", session_id="s", status="COMPLETED", priority="high", department_id="gm", department_name="General Medicine",
        doctor_id="d", doctor_name="Koel Kamra", chief_complaint="fever", demographics={"name": name, "age": "34", "sex": "male"},
        hms_patient_id=mrn, review_decision="approve", missing_count=0, emergency=True,
        appointment_start=start, appointment_booked=True, created_at=NOW - timedelta(days=9), updated_at=None,
    )


def test_one_row_per_patient_newest_first_and_no_clinical_fields():
    rows = patient_directory.build([
        item("454", NOW - timedelta(days=5)), item("454", NOW - timedelta(days=1)),
        item("330", NOW, name="Neha Joshi"), item(None, None, name="abandoned intake"),
    ])
    assert [r.hms_patient_id for r in rows] == ["330", "454"]
    assert rows[1].visit_count == 2 and rows[1].visits[0].appointment_start == NOW - timedelta(days=1)
    dumped = str([r.model_dump() for r in rows])
    assert "fever" not in dumped and "high" not in dumped
    assert CLINICAL.isdisjoint(rows[0].model_dump()) and CLINICAL.isdisjoint(rows[0].visits[0].model_dump())
