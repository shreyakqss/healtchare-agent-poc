"""A red flag in the chat: the interview stops with the ambulance advice, the OpenEMR chart gets
the emergency note at once, the case reaches the doctor despite missing answers, and the patient
is never offered a booking. Real OpenEMR; only the intake LLM agents are faked."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.integrations.hms import get_hms
from app.main import app
from app.models import AuditEvent, PatientCase
from app.services import emergency_service
from tests.helpers import BASE, new_identified_session, patch_intake_agents, wait_for_status

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_severe_chest_pain_stops_intake_records_the_emergency_and_offers_no_booking(client, monkeypatch):
    patch_intake_agents(monkeypatch)
    sid, cid = new_identified_session(client)

    turn = client.post(f"{BASE}/intake-sessions/{sid}/messages", json={"content": "severe chest pain since morning"}).json()
    assert turn["intake_complete"] is True and turn["asks_field"] is None
    assert "Call an ambulance now on 108" in turn["reply"]

    with SessionLocal() as db:
        case = db.get(PatientCase, uuid.UUID(cid))
        assert case.emergency_flagged_at is not None
        written = db.query(AuditEvent).filter_by(case_id=case.id, action=emergency_service.WRITTEN).one()
        mrn = case.hms_patient_id
    assert written.payload["reference"]
    titles = [d.title for d in get_hms().list_documents(mrn, limit=50)]
    assert any("EMERGENCY" in (t or "") or "emergency" in (t or "") for t in titles), titles

    wait_for_status(client, cid, "NEEDS_REVIEW")  # reaches the doctor although answers are missing
    patient_view = client.get(f"{BASE}/cases/{cid}/patient").json()
    assert patient_view["emergency"]["ambulance_number"] == "108"
    assert patient_view["routing"]["slot_options"] == [] and patient_view["routing"]["doctor_choice"] is False
    assert "priority" not in str(patient_view["emergency"])
