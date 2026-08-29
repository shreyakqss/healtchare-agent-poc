"""Consent, review and finalisation gates over the real API.

Needs Postgres and the OpenEMR from backend/.env: the identity form registers a real
patient and every clinician action is verified against a real OpenEMR login.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.helpers import (
    BASE,
    DOCTOR_CREDENTIALS,
    FINALIZER_CREDENTIALS,
    IDENTITY_FORM,
    REVIEWER_CREDENTIALS,
    RejectingHMS,
    answer_clinical_questions,
    new_identified_session,
    patch_intake_agents,
    skip_required_attachments,
    wait_for_status,
)

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def fake_llm(monkeypatch):
    patch_intake_agents(monkeypatch)


def test_consent_then_review_gate(client, monkeypatch):
    s = client.post(f"{BASE}/intake-sessions", json={}).json()
    sid, cid = s["session_id"], s["case_id"]

    assert client.post(f"{BASE}/intake-sessions/{sid}/identity", json=IDENTITY_FORM).status_code == 403
    client.post(f"{BASE}/intake-sessions/{sid}/consent", json={"granted": True})
    assert client.post(f"{BASE}/intake-sessions/{sid}/identity", json=IDENTITY_FORM).status_code == 200
    skip_required_attachments(client, cid)
    assert client.post(f"{BASE}/intake-sessions/{sid}/messages", json={"content": "knee pain for a week"}).status_code == 200

    review = {"decision": "approve", **REVIEWER_CREDENTIALS}
    assert client.post(f"{BASE}/cases/{cid}/review", json=review).status_code == 409
    d = client.post(f"{BASE}/cases/{cid}/prescreen").json()
    assert d["status"] == "NEEDS_REVIEW"
    assert client.get(f"{BASE}/cases/{cid}").json()["triage"]["rule_codes"]
    assert client.post(f"{BASE}/cases/{cid}/finalize", json=FINALIZER_CREDENTIALS).status_code == 409
    assert client.post(f"{BASE}/cases/{cid}/consultation-notes", json={**DOCTOR_CREDENTIALS, "notes": "n"}).status_code == 409

    # NEEDS_REVIEW: the state gate no longer blocks, so a failed identity check must 401.
    monkeypatch.setattr("app.services.clinician_identity.get_hms", lambda: RejectingHMS())
    assert client.post(f"{BASE}/cases/{cid}/review", json=review).status_code == 401


def test_finalize_requires_clinician_credentials(client, monkeypatch):
    """/finalize carries the same credential gate as /review and /consultation-notes: 401
    when the hospital system rejects the login, and the verified identity - the OpenEMR
    Practitioner the login resolves to - lands on the care task."""
    sid, cid = new_identified_session(client)
    skip_required_attachments(client, cid)
    answer_clinical_questions(client, sid, opening="ankle pain for two days")
    wait_for_status(client, cid, "NEEDS_REVIEW")  # fired in the background on completion

    review = client.post(f"{BASE}/cases/{cid}/review", json={"decision": "approve", **REVIEWER_CREDENTIALS})
    assert review.status_code == 201, review.text
    reviewer_id = review.json()["reviewer_id"]
    assert client.post(f"{BASE}/cases/{cid}/review", json={"decision": "approve", **REVIEWER_CREDENTIALS}).status_code == 409
    note = client.post(f"{BASE}/cases/{cid}/consultation-notes", json={**DOCTOR_CREDENTIALS, "notes": "Advised rest and ice."})
    assert note.status_code == 201, note.text

    monkeypatch.setattr("app.services.clinician_identity.get_hms", lambda: RejectingHMS())
    assert client.post(f"{BASE}/cases/{cid}/finalize", json=FINALIZER_CREDENTIALS).status_code == 401
    monkeypatch.undo()

    good = client.post(f"{BASE}/cases/{cid}/finalize", json=FINALIZER_CREDENTIALS)
    assert good.status_code == 200, good.text
    care_tasks = good.json()["care_tasks"]
    assert care_tasks and care_tasks[0]["status"] == "draft"
    # Attributed to the verified hospital-system identity, not the typed-in username.
    assert care_tasks[0]["payload"]["finalized_by"] == reviewer_id
    assert client.post(f"{BASE}/cases/{cid}/finalize", json=FINALIZER_CREDENTIALS).status_code == 409


def test_roster_and_clinic_come_from_the_hospital_system(client):
    roster = client.get(f"{BASE}/hospital/roster").json()
    assert roster["source"] == "hms", "practitioners should be read from the hospital system"
    assert roster["doctors"], "the hospital system has no practitioners on file"
    assert {"id", "name", "department_id", "specialty", "working_days"} <= set(roster["doctors"][0])
    # Every listed doctor matched a configured department - "unknown" is never routable.
    assert all(d["department_id"] != "unknown" for d in roster["doctors"])

    hospital = client.get(f"{BASE}/hospital/config").json()["hospital"]
    assert hospital["source"] == "hms" and hospital["name"]
