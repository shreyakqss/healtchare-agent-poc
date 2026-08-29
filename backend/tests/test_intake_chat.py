"""Step 2 of intake: the clinical chat turn loop, POST /intake-sessions/{id}/messages
(needs Postgres from .env).

The fact extractor and question planner are replaced with deterministic fakes: these tests
exercise the turn-loop MECHANICS (which field gets asked, how a denial settles a field, the
MAX_ASSISTANT_QUESTIONS backstop, the HMS-import skip), not the model's judgement.
"""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

import app.services.intake_service as intake_service_module
from app.agents.schemas import ExtractionResult
from app.main import app
from tests.helpers import (
    BASE,
    new_identified_session,
    patch_intake_agents,
    require_attachments,
    skip_required_attachments,
)

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def fake_llm(monkeypatch):
    patch_intake_agents(monkeypatch)
    require_attachments(monkeypatch, "test-only-prescreen-blocker")


def test_chat_asks_clinical_fields_one_at_a_time_then_completes(client):
    sid, cid = new_identified_session(client)

    r0 = client.post(f"{BASE}/intake-sessions/{sid}/messages", json={"content": "I have a persistent cough"}).json()
    # turn 0: reason_for_visit is auto-filled from the opening statement; symptom is next.
    assert r0["asks_field"] == "symptom"
    assert r0["intake_complete"] is False
    assert set(r0["missing_fields"]) == {"symptom", "duration", "history", "medication", "allergy"}

    for field in ["duration", "history", "medication", "allergy"]:
        r = client.post(f"{BASE}/intake-sessions/{sid}/messages", json={"content": "no"}).json()
        assert r["asks_field"] == field

    last = client.post(f"{BASE}/intake-sessions/{sid}/messages", json={"content": "no"}).json()
    assert last["intake_complete"] is True
    assert last["missing_fields"] == []

    detail = client.get(f"{BASE}/cases/{cid}").json()
    facts = {f["kind"]: f["value"] for f in detail["facts"]}
    assert facts["symptom"] == "None reported by patient"
    assert facts["history"] == "None reported by patient"
    entries = {(e["kind"], e["name"]) for e in detail["allergies_medications"]}
    assert ("medication", "None reported by patient") in entries
    assert ("allergy", "None reported by patient") in entries


def test_chat_max_assistant_questions_backstop(client, monkeypatch):
    monkeypatch.setattr(intake_service_module, "MAX_ASSISTANT_QUESTIONS", 1)
    sid, _ = new_identified_session(client)

    r0 = client.post(f"{BASE}/intake-sessions/{sid}/messages", json={"content": "chest pain"}).json()
    assert r0["asks_field"] == "symptom"
    assert r0["intake_complete"] is False

    # One assistant question asked - the backstop closes the conversation on the next turn.
    r1 = client.post(f"{BASE}/intake-sessions/{sid}/messages", json={"content": "no"}).json()
    assert r1["intake_complete"] is True
    assert r1["reply"] == intake_service_module.CLOSING_WITH_GAPS
    assert r1["missing_fields"] != []


def test_chat_completion_fires_prescreen(client, monkeypatch):
    """Once every required field is present and every required attachment kind is resolved,
    prescreen fires in the background. run_prescreen is replaced with a spy."""
    fired: list[str] = []

    async def fake_run_prescreen(case_id, **_) -> None:
        fired.append(str(case_id))

    monkeypatch.setattr("app.services.workflow_jobs.run_prescreen", fake_run_prescreen)
    require_attachments(monkeypatch)

    sid, cid = new_identified_session(client)
    skip_required_attachments(client, cid)
    for msg in ["cough", "no", "no", "no", "no", "no"]:
        client.post(f"{BASE}/intake-sessions/{sid}/messages", json={"content": msg})

    for _ in range(20):
        if fired:
            break
        time.sleep(0.1)
    assert fired == [cid]


def test_chat_completion_does_not_fire_prescreen_with_pending_attachments(client, monkeypatch):
    fired: list[str] = []

    async def fake_run_prescreen(case_id, **_) -> None:
        fired.append(str(case_id))

    monkeypatch.setattr("app.services.workflow_jobs.run_prescreen", fake_run_prescreen)
    require_attachments(monkeypatch, "lab_report", "prescription")

    sid, _ = new_identified_session(client)
    # Both required attachments deliberately left unresolved.
    for msg in ["cough", "no", "no", "no", "no", "no"]:
        client.post(f"{BASE}/intake-sessions/{sid}/messages", json={"content": msg})

    time.sleep(0.3)
    assert fired == []


def test_off_topic_reply_does_not_settle_the_field_or_call_the_llm(client, monkeypatch):
    """An off-topic question ("what are the 2026 movies") must leave the field open, redirect
    without touching the extractor or planner, and only settle once a real answer arrives."""
    calls = {"extract": 0, "plan": 0}

    async def counting_extract(message: str) -> ExtractionResult:
        calls["extract"] += 1
        return ExtractionResult(facts=[], allergies_medications=[])

    async def counting_plan(ctx, on_token=None) -> str:
        calls["plan"] += 1
        if on_token:
            on_token("(mock question)")
        return "(mock question)"

    monkeypatch.setattr(intake_service_module.fact_extractor, "extract", counting_extract)
    monkeypatch.setattr(intake_service_module.question_planner, "plan", counting_plan)

    sid, _ = new_identified_session(client)

    r0 = client.post(f"{BASE}/intake-sessions/{sid}/messages", json={"content": "I have a persistent cough"}).json()
    assert r0["asks_field"] == "symptom"
    calls_after_opening = dict(calls)

    r1 = client.post(f"{BASE}/intake-sessions/{sid}/messages", json={"content": "what are the 2026 movies"}).json()
    assert r1["asks_field"] == "symptom"
    assert "symptom" in r1["missing_fields"]
    assert calls["extract"] == calls_after_opening["extract"], "the extractor must not run on an off-topic message"
    assert calls["plan"] == calls_after_opening["plan"], "the planner must not run on an off-topic message"

    r2 = client.post(f"{BASE}/intake-sessions/{sid}/messages", json={"content": "no"}).json()
    assert r2["asks_field"] == "duration"
    assert calls["extract"] == calls_after_opening["extract"] + 1, "a real answer should still reach the extractor"


def test_patient_cannot_link_an_arbitrary_hospital_record(client):
    response = client.post(f"{BASE}/intake-sessions", json={"mrn": "someone-elses-record"})
    assert response.status_code == 422
