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
from app.agents import AgentUnavailable
from app.agents.schemas import ExtractedFact, ExtractionResult, PatientAnswerReview
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


def test_out_of_scope_question_is_refused_and_leaves_the_field_open(client, monkeypatch):
    calls = {"extract": 0, "plan": 0, "answer": 0}

    async def counting_extract(message, asked_field, asked_question, transcript, vocabulary) -> ExtractionResult:
        calls["extract"] += 1
        if asked_field is None:
            return ExtractionResult(
                facts=[ExtractedFact(kind="reason_for_visit", value=message)],
                current_question_response="not_answered",
            )
        if message.endswith("?"):
            return ExtractionResult(
                current_question_response="not_answered",
                patient_question=message,
                question_scope="out_of_scope",
            )
        return ExtractionResult(current_question_response="denied")

    async def counting_plan(ctx, on_token=None) -> str:
        calls["plan"] += 1
        if on_token:
            on_token("(mock question)")
        return "(mock question)"

    async def counting_answer(question, reference, transcript, asks_for) -> str:
        calls["answer"] += 1
        return "(mock answer)"

    monkeypatch.setattr(intake_service_module.fact_extractor, "extract", counting_extract)
    monkeypatch.setattr(intake_service_module.question_planner, "plan", counting_plan)
    monkeypatch.setattr(intake_service_module.patient_assistant, "answer", counting_answer)

    sid, _ = new_identified_session(client)

    r0 = client.post(f"{BASE}/intake-sessions/{sid}/messages", json={"content": "I have a persistent cough"}).json()
    assert r0["asks_field"] == "symptom"
    calls_after_opening = dict(calls)

    r1 = client.post(f"{BASE}/intake-sessions/{sid}/messages", json={"content": "what are the 2026 movies?"}).json()
    assert r1["asks_field"] == "symptom"
    assert "symptom" in r1["missing_fields"]
    assert "outside healthcare" in r1["reply"]
    assert calls["answer"] == calls_after_opening["answer"]
    assert calls["extract"] == calls_after_opening["extract"] + 1, "the extractor classifies the message"
    assert calls["plan"] == calls_after_opening["plan"], "the planner must not run on a question"

    r2 = client.post(f"{BASE}/intake-sessions/{sid}/messages", json={"content": "no"}).json()
    assert r2["asks_field"] == "duration"
    assert calls["extract"] == calls_after_opening["extract"] + 2, "a real answer should still reach the extractor"


def test_mixed_answer_and_health_question_keeps_both(client, monkeypatch):
    calls: dict[str, object] = {}

    async def mixed_extract(message, asked_field, asked_question, transcript, vocabulary) -> ExtractionResult:
        if asked_field is None:
            return ExtractionResult(
                facts=[ExtractedFact(kind="reason_for_visit", value="persistent cough")],
                current_question_response="not_answered",
            )
        calls["context"] = transcript
        return ExtractionResult(
            facts=[ExtractedFact(kind="symptom", value="dry cough")],
            current_question_response="answered",
            patient_question="What is a cough?",
            question_scope="general_health",
            health_topic="cough definition",
        )

    async def resolve(db, case_id, scope, health_topic=None):
        calls["resolve"] = (scope, health_topic)
        return '{"topic":"cough definition","results":[]}'

    async def answer(question, reference, transcript, asks_for) -> str:
        calls["answer"] = (question, reference, transcript, asks_for)
        return "A cough is a protective reflex."

    monkeypatch.setattr(intake_service_module.fact_extractor, "extract", mixed_extract)
    monkeypatch.setattr(intake_service_module.assistant_tools, "resolve", resolve)
    monkeypatch.setattr(intake_service_module.patient_assistant, "answer", answer)

    sid, cid = new_identified_session(client)
    client.post(f"{BASE}/intake-sessions/{sid}/messages", json={"content": "persistent cough"})
    result = client.post(
        f"{BASE}/intake-sessions/{sid}/messages",
        json={"content": "I have a dry cough. What is a cough?"},
    ).json()

    assert result["asks_field"] == "duration"
    assert "symptom" not in result["missing_fields"]
    assert "protective reflex" in result["reply"]
    assert calls["resolve"] == ("general_health", "cough definition")
    assert calls["answer"][3] == "how long the symptoms have lasted"
    assert calls["context"][-1]["role"] == "assistant"
    detail = client.get(f"{BASE}/cases/{cid}").json()
    assert any(fact["kind"] == "symptom" and fact["value"] == "dry cough" for fact in detail["facts"])


def test_written_xray_report_question_is_explained(client, monkeypatch):
    async def understand(message, asked_field, asked_question, transcript, vocabulary) -> ExtractionResult:
        if asked_field is None:
            return ExtractionResult(
                facts=[ExtractedFact(kind="reason_for_visit", value="review X-ray report")],
                current_question_response="not_answered",
            )
        return ExtractionResult(
            current_question_response="not_answered",
            patient_question="Does the opacity in my written X-ray report mean cancer?",
            question_scope="personal_record",
        )

    async def resolve(db, case_id, scope, health_topic=None):
        assert scope == "personal_record"
        return '{"documents":[{"kind":"Radiology Report","text":"Small opacity at left base"}]}'

    async def answer(question, reference, transcript, asks_for) -> str:
        assert "opacity" in question
        assert "Small opacity" in reference
        return "Opacity describes a denser area on the written X-ray report; by itself it does not establish a cancer diagnosis."

    monkeypatch.setattr(intake_service_module.fact_extractor, "extract", understand)
    monkeypatch.setattr(intake_service_module.assistant_tools, "resolve", resolve)
    monkeypatch.setattr(intake_service_module.patient_assistant, "answer", answer)

    sid, _ = new_identified_session(client)
    client.post(f"{BASE}/intake-sessions/{sid}/messages", json={"content": "I want to review my X-ray"})
    result = client.post(
        f"{BASE}/intake-sessions/{sid}/messages",
        json={"content": "Does that opacity mean cancer?"},
    ).json()

    assert "does not establish a cancer diagnosis" in result["reply"]
    assert result["asks_field"] == "symptom"


def test_irrelevant_statement_does_not_settle_the_current_field(client, monkeypatch):
    async def understand(message, asked_field, asked_question, transcript, vocabulary) -> ExtractionResult:
        if asked_field is None:
            return ExtractionResult(
                facts=[ExtractedFact(kind="reason_for_visit", value=message)],
                current_question_response="not_answered",
            )
        return ExtractionResult(current_question_response="not_answered")

    monkeypatch.setattr(intake_service_module.fact_extractor, "extract", understand)
    sid, cid = new_identified_session(client)
    client.post(f"{BASE}/intake-sessions/{sid}/messages", json={"content": "persistent cough"})
    result = client.post(f"{BASE}/intake-sessions/{sid}/messages", json={"content": "I watched a movie"}).json()

    assert result["asks_field"] == "symptom"
    assert "symptom" in result["missing_fields"]
    detail = client.get(f"{BASE}/cases/{cid}").json()
    assert not any(fact["kind"] == "symptom" for fact in detail["facts"])


def test_extractor_outage_does_not_store_or_settle_unread_content(client, monkeypatch):
    sid, cid = new_identified_session(client)
    client.post(f"{BASE}/intake-sessions/{sid}/messages", json={"content": "persistent cough"})

    async def unavailable(message, asked_field, asked_question, transcript, vocabulary) -> ExtractionResult:
        raise AgentUnavailable("test outage")

    monkeypatch.setattr(intake_service_module.fact_extractor, "extract", unavailable)
    result = client.post(f"{BASE}/intake-sessions/{sid}/messages", json={"content": "tell me a joke"}).json()

    assert result["asks_field"] is None
    assert "symptom" in result["missing_fields"]
    assert "could not process" in result["reply"]
    detail = client.get(f"{BASE}/cases/{cid}").json()
    assert not any(fact["kind"] == "symptom" for fact in detail["facts"])


def test_unsafe_generated_answer_is_blocked_before_delivery(client, monkeypatch):
    async def understand(message, asked_field, asked_question, transcript, vocabulary) -> ExtractionResult:
        if asked_field is None:
            return ExtractionResult(
                facts=[ExtractedFact(kind="reason_for_visit", value=message)],
                current_question_response="not_answered",
            )
        return ExtractionResult(
            current_question_response="not_answered",
            patient_question=message,
            question_scope="general_health",
            health_topic="headache",
        )

    async def resolve(*_):
        return '{"topic":"headache","results":[]}'

    async def unsafe_answer(*_, **__):
        return "You definitely have a migraine and should double your medication."

    async def block(scope: str, question: str, reference: str, answer: str) -> PatientAnswerReview:
        return PatientAnswerReview(decision="block")

    monkeypatch.setattr(intake_service_module.fact_extractor, "extract", understand)
    monkeypatch.setattr(intake_service_module.assistant_tools, "resolve", resolve)
    monkeypatch.setattr(intake_service_module.patient_assistant, "answer", unsafe_answer)
    monkeypatch.setattr(intake_service_module.answer_guard, "check", block)

    sid, _ = new_identified_session(client)
    client.post(f"{BASE}/intake-sessions/{sid}/messages", json={"content": "headache"})
    result = client.post(f"{BASE}/intake-sessions/{sid}/messages", json={"content": "What could this be?"}).json()

    assert "double your medication" not in result["reply"]
    assert "safe, reliable answer" in result["reply"]
    assert result["asks_field"] == "symptom"


def test_only_a_configured_clinic_term_is_stored_as_normalized():
    vocabulary = ["chest pain", "shortness of breath"]
    assert intake_service_module._clinic_term("Shortness Of Breath ", vocabulary) == "shortness of breath"
    assert intake_service_module._clinic_term("myocardial infarction", vocabulary) == ""
    assert intake_service_module._clinic_term("", vocabulary) == ""


def test_patient_cannot_link_an_arbitrary_hospital_record(client):
    response = client.post(f"{BASE}/intake-sessions", json={"mrn": "someone-elses-record"})
    assert response.status_code == 422
