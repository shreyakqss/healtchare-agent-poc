"""Confirming a time books it on the doctor's real OpenEMR calendar - no clinician approval -
and moving it, or a rejected case, takes the old booking off again."""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.integrations.hms import get_hms
from app.integrations.hms.openemr import provisioning
from app.main import app
from app.models import IntakeSession, PatientCase, RoutingRecommendation
from app.services import appointment_service
from tests.helpers import new_identified_session

pytestmark = pytest.mark.integration


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def calendar_row(event_id: str) -> dict | None:
    with provisioning._transaction() as cur:
        cur.execute("SELECT pc_aid, pc_pid, pc_catid, pc_eventDate, pc_startTime FROM openemr_postcalendar_events"
                    " WHERE pc_eid = %s", (int(event_id),))
        return cur.fetchone()


def test_confirmed_time_lands_on_the_doctors_calendar_and_moves_with_the_patient(client):
    hms = get_hms()
    doctor, slots = next(
        ((p, s) for p in hms.list_practitioners() if len(s := [x.model_dump(mode="json") for x in
         hms.available_slots(p.department_id, p.id, limit=6)]) >= 2 and s[0]["id"].startswith("hours-")),
        (None, None),
    )
    if doctor is None:
        pytest.skip("no OpenEMR practitioner with office hours")
    _, case_id = new_identified_session(client)
    with SessionLocal() as db:
        case = db.get(PatientCase, uuid.UUID(case_id))
        db.get(IntakeSession, case.session_id).status = "NEEDS_REVIEW"
        db.add(RoutingRecommendation(
            case_id=case.id, department_id=doctor.department_id, department_name="Test", doctor_id=doctor.id,
            doctor_name=doctor.name, appointment_type_id="consult", appointment_type_label="Consult",
            rationale="test", matched_keywords=[], suggested_slot=slots[0], slot_options=slots,
        ))
        db.commit()

    with SessionLocal() as db:
        appointment_service.select_slot(db, db.get(PatientCase, uuid.UUID(case_id)), slots[0]["id"])
    with SessionLocal() as db:
        first = db.get(PatientCase, uuid.UUID(case_id)).hms_appointment_id
    row = calendar_row(first)
    assert row and row["pc_catid"] == provisioning.OFFICE_VISIT and row["pc_aid"] == str(provisioning.user_id_for(doctor.id))
    assert slots[0]["id"] not in [s.id for s in hms.available_slots(doctor.department_id, doctor.id, limit=6)]

    with SessionLocal() as db:
        appointment_service.select_slot(db, db.get(PatientCase, uuid.UUID(case_id)), slots[1]["id"])
    with SessionLocal() as db:
        second = db.get(PatientCase, uuid.UUID(case_id)).hms_appointment_id
    assert second != first and calendar_row(first) is None and calendar_row(second)

    with SessionLocal() as db:
        appointment_service.release_booking(db, db.get(PatientCase, uuid.UUID(case_id)), "test")
    assert calendar_row(second) is None
