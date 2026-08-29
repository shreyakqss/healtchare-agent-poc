"""Step 1 of intake: POST /intake-sessions/{id}/identity (needs Postgres from .env).

Pure fact writes plus the HMS patient registration - no LLM involved.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.helpers import BASE, identity_form, new_consented_session

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_identity_happy_path(client):
    sid, cid = new_consented_session(client)
    payload = identity_form(name="Priya Nair", contact_preference="email", email="priya@example.test")
    res = client.post(f"{BASE}/intake-sessions/{sid}/identity", json=payload)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["case_id"] == cid
    assert body["demographics"]["name"] == "Priya Nair"
    assert body["hms_linked"] is True  # registration returned an MRN for the new record
    for field in ("name", "age", "gender", "contact_preference"):
        assert field not in body["missing_fields"]
    # Clinical fields are untouched by the identity step - still outstanding.
    assert "reason_for_visit" in body["missing_fields"]

    detail = client.get(f"{BASE}/cases/{cid}").json()
    kinds = {f["kind"] for f in detail["facts"]}
    assert {"name", "age", "gender", "contact_preference"} <= kinds
    assert detail["hms_patient_id"]


def test_identity_422_when_required_field_missing(client):
    sid, _ = new_consented_session(client)
    res = client.post(f"{BASE}/intake-sessions/{sid}/identity", json=identity_form(name=""))
    assert res.status_code == 422


def test_identity_requires_consent(client):
    s = client.post(f"{BASE}/intake-sessions", json={}).json()
    res = client.post(f"{BASE}/intake-sessions/{s['session_id']}/identity", json=identity_form())
    assert res.status_code == 403


def test_identity_rejects_future_birth_date(client):
    sid, _ = new_consented_session(client)
    res = client.post(f"{BASE}/intake-sessions/{sid}/identity", json=identity_form(birth_date="2999-01-01"))
    assert res.status_code == 422


def test_identity_cannot_be_submitted_twice(client):
    sid, _ = new_consented_session(client)
    assert client.post(f"{BASE}/intake-sessions/{sid}/identity", json=identity_form()).status_code == 200
    assert client.post(f"{BASE}/intake-sessions/{sid}/identity", json=identity_form()).status_code == 409


def test_clinical_chat_requires_identity(client):
    sid, _ = new_consented_session(client)
    res = client.post(f"{BASE}/intake-sessions/{sid}/messages", json={"content": "headache"})
    assert res.status_code == 409
