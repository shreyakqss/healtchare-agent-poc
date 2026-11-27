"""Follow-up vs new visits, and registering once (needs Postgres from .env and OpenEMR).

A returning patient is not asked who they are again: the identity step is filled from their
hospital record. A follow-up must be about one of the patient's own completed visits.
"""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.domain import routing
from app.main import app
from tests.helpers import BASE, IDENTITY_FORM, new_identified_session

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_doctor_first_puts_previous_doctor_on_top_and_flags_it():
    slots = [
        {"id": "a", "practitioner_id": "x", "start": "2026-11-04T10:00:00+05:30"},
        {"id": "b", "practitioner_id": "prev", "start": "2026-11-04T11:00:00+05:30"},
        {"id": "c", "practitioner_id": "prev", "start": "2026-11-04T12:00:00+05:30"},
    ]
    ordered = routing.doctor_first(slots, "prev")
    assert [s["id"] for s in ordered] == ["b", "c", "a"]
    assert ordered[0]["previous_doctor"] is True and "previous_doctor" not in ordered[2]


def test_follow_up_needs_the_visit_it_follows(client):
    res = client.post(f"{BASE}/intake-sessions", json={"visit_type": "follow_up"})
    assert res.status_code == 422


def test_follow_up_of_a_visit_that_is_not_yours_is_refused(client):
    res = client.post(f"{BASE}/intake-sessions", json={"visit_type": "follow_up", "follow_up_of": str(uuid.uuid4())})
    assert res.status_code == 409


def test_follow_up_options_lists_only_completed_visits(client):
    res = client.get(f"{BASE}/intake-sessions/follow-up-options")
    assert res.status_code == 200
    for visit in res.json():
        assert {"case_id", "visit_at", "diagnosis", "prescription", "advice"} <= visit.keys()


def test_registered_patient_skips_identity_on_the_next_visit(client):
    sid, cid = new_identified_session(client)
    # Close the first session so the next start is a fresh visit, not a resume.
    from app.db import db_session
    from app.domain.lifecycle import CaseStatus
    from app.models import IntakeSession

    with db_session() as db:
        db.get(IntakeSession, uuid.UUID(sid)).status = CaseStatus.REJECTED
        db.commit()

    nxt = client.post(f"{BASE}/intake-sessions", json={}).json()
    assert nxt["hms_linked"] is True  # same hospital record, no duplicate registration
    consented = client.post(f"{BASE}/intake-sessions/{nxt['session_id']}/consent", json={"granted": True}).json()
    assert consented["identity_complete"] is True
    for field in ("name", "age", "gender", "contact_preference"):
        assert field not in consented["missing_fields"]
    again = client.post(f"{BASE}/intake-sessions/{nxt['session_id']}/identity", json=IDENTITY_FORM)
    assert again.status_code == 409


def test_profile_edit_writes_the_patients_own_record(client):
    new_identified_session(client)
    res = client.put(f"{BASE}/intake-sessions/profile", json={**IDENTITY_FORM, "city": "Mumbai"})
    assert res.status_code == 200, res.text
    assert res.json()["city"] == "Mumbai"
    client.put(f"{BASE}/intake-sessions/profile", json=IDENTITY_FORM)
