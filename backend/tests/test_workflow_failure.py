"""A workflow step that raises must fail the run - never be skipped (needs Postgres from .env).

agno's default `on_error="skip"` would let prescreen reach NEEDS_REVIEW with no routing
recommendation; `workflows/common.step()` turns that off.
"""

import asyncio
import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.workflows import run_prescreen
from tests.helpers import (
    BASE,
    DOCTOR_CREDENTIALS,
    FINALIZER_CREDENTIALS,
    REVIEWER_CREDENTIALS,
    answer_clinical_questions,
    new_identified_session,
    patch_intake_agents,
    require_attachments,
    skip_required_attachments,
    wait_for_status,
)

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


class _BrokenSlotsHMS:
    def get_patient(self, mrn):
        return None

    def list_practitioners(self):
        return []

    def available_slots(self, department_id, practitioner_id=None, limit=5):
        raise ConnectionError("HMS slot search exploded")


class _RefusingAppointmentsHMS:
    """An HMS that accepts documents but has no appointment write (live OpenEMR 8.3)."""

    def push_document(self, mrn, title, content, content_type="text/plain"):
        return "DOC-OK"

    def sync_reviewed_intake(self, mrn, payload):
        return None

    def request_appointment(self, request):
        raise ConnectionError("no Appointment endpoint")

    def get_facility(self):
        return None


def test_hms_refusing_appointment_request_still_finalises_with_a_draft_task(client, monkeypatch):
    patch_intake_agents(monkeypatch)
    sid, cid = new_identified_session(client)
    skip_required_attachments(client, cid)
    answer_clinical_questions(client, sid)
    wait_for_status(client, cid, "NEEDS_REVIEW")
    assert client.post(f"{BASE}/cases/{cid}/review", json={"decision": "approve", **REVIEWER_CREDENTIALS}).status_code == 201
    assert client.post(f"{BASE}/cases/{cid}/consultation-notes", json={**DOCTOR_CREDENTIALS, "notes": "n"}).status_code == 201

    monkeypatch.setattr("app.workflows.finalize.get_hms", lambda: _RefusingAppointmentsHMS())
    res = client.post(f"{BASE}/cases/{cid}/finalize", json=FINALIZER_CREDENTIALS)
    assert res.status_code == 200, res.text
    detail = res.json()
    assert detail["status"] == "COMPLETED"
    assert detail["care_tasks"][0]["status"] == "draft" and detail["care_tasks"][0]["hms_reference"] is None
    actions = [e["action"] for e in client.get(f"{BASE}/cases/{cid}/audit").json()]
    assert "care_task.hms_request_failed" in actions


def test_failing_step_marks_case_failed_and_audits(client, monkeypatch):
    patch_intake_agents(monkeypatch)
    # Hold the case in intake so this test is the only thing that ever runs the workflow:
    # left unrequired, the closing turn fires pre-screening in the background against the
    # real hospital system, and the routing it legitimately writes is not what is under test.
    require_attachments(monkeypatch, "lab_report")
    sid, cid = new_identified_session(client)
    for msg in ["knee pain for a week", "no", "no", "no", "no", "no"]:
        client.post(f"{BASE}/intake-sessions/{sid}/messages", json={"content": msg})

    monkeypatch.setattr("app.workflows.prescreen.get_hms", lambda: _BrokenSlotsHMS())
    with pytest.raises(Exception, match="slot search exploded"):
        asyncio.run(run_prescreen(uuid.UUID(cid)))

    detail = client.get(f"{BASE}/cases/{cid}").json()
    assert detail["status"] == "FAILED"
    assert detail["routing"] is None
    actions = [e["action"] for e in client.get(f"{BASE}/cases/{cid}/audit").json()]
    assert "workflow.failed" in actions
    assert "summary.prescreening_generated" not in actions  # later steps did not run
