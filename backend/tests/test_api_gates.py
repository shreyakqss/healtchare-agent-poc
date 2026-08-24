"""Review gate and consent gate over the real API (needs Postgres from .env)."""

import pytest
from fastapi.testclient import TestClient

from app.main import app

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_consent_then_review_gate(client):
    base = "/api/v1/healthcare"
    s = client.post(f"{base}/intake-sessions", json={}).json()
    sid, cid = s["session_id"], s["case_id"]

    assert client.post(f"{base}/intake-sessions/{sid}/messages", json={"content": "hi"}).status_code == 403
    client.post(f"{base}/intake-sessions/{sid}/consent", json={"granted": True})
    assert client.post(f"{base}/intake-sessions/{sid}/messages", json={"content": "knee pain for a week"}).status_code == 200

    assert client.post(f"{base}/cases/{cid}/review", json={"decision": "approve", "reviewer_id": "x"}).status_code == 409
    d = client.post(f"{base}/cases/{cid}/prescreen").json()
    assert d["status"] == "NEEDS_REVIEW" and d["triage"]["rule_codes"]
    assert client.post(f"{base}/cases/{cid}/finalize").status_code == 409
    assert client.post(f"{base}/cases/{cid}/consultation-notes", json={"doctor_id": "d", "notes": "n"}).status_code == 409