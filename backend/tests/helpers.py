"""Shared fixtures for the integration tests.

These run against the OpenEMR configured in `backend/.env`: the identity form registers a
real patient, and every clinician action is verified against a real OpenEMR login. The intake
agents are stubbed because these tests cover turn-loop mechanics, not model quality.
"""

from __future__ import annotations

import time
from typing import Any

import app.services.intake_service as intake_service_module
from app.agents.schemas import ExtractedFact, ExtractionResult, PatientAnswerReview
from app.core.config import settings

BASE = "/api/v1/healthcare"

# Named so records this suite leaves in the test OpenEMR are obvious.
IDENTITY_FORM: dict[str, Any] = {
    "name": "CareFlow Test Patient",
    "birth_date": "1986-03-12",
    "gender": "female",
    "phone": "+91 90000 00000",
    "address_line1": "12 Test Road",
    "city": "Pune",
    "state": "Maharashtra",
    "postal_code": "411001",
    "country": "India",
    "contact_preference": "phone",
}

# A real OpenEMR login: /review, /consultation-notes and /finalize each verify it through
# the OAuth2 password grant, so there is nothing to stub.
CLINICIAN = {"username": settings.OPENEMR_USERNAME or "", "password": settings.OPENEMR_PASSWORD or ""}
REVIEWER_CREDENTIALS = {"reviewer_username": CLINICIAN["username"], "reviewer_password": CLINICIAN["password"]}
DOCTOR_CREDENTIALS = {"doctor_username": CLINICIAN["username"], "doctor_password": CLINICIAN["password"]}
FINALIZER_CREDENTIALS = {"finalizer_username": CLINICIAN["username"], "finalizer_password": CLINICIAN["password"]}


def identity_form(**overrides: Any) -> dict[str, Any]:
    return {**IDENTITY_FORM, **overrides}


async def fake_extract(
    message: str,
    asked_field: str | None,
    asked_question: str | None,
    transcript: list[dict[str, str]],
    vocabulary: list[str],
) -> ExtractionResult:
    text = message.strip().lower()
    if text.endswith("?"):
        return ExtractionResult(
            current_question_response="not_answered",
            patient_question=message,
            question_scope="out_of_scope",
        )
    response = "denied" if text in {"no", "none"} else "answered" if asked_field else "not_answered"
    facts = [ExtractedFact(kind="reason_for_visit", value=message)] if asked_field is None else []
    return ExtractionResult(facts=facts, current_question_response=response)


async def fake_plan(ctx, on_token=None) -> str:
    if on_token:
        on_token("(mock question)")
    return "(mock question)"


async def fake_answer(question, reference, transcript, asks_for) -> str:
    return "(mock answer)"


async def fake_answer_review(scope: str, question: str, reference: str, answer: str) -> PatientAnswerReview:
    return PatientAnswerReview(decision="allow")


def patch_intake_agents(monkeypatch) -> None:
    monkeypatch.setattr(intake_service_module.fact_extractor, "extract", fake_extract)
    monkeypatch.setattr(intake_service_module.question_planner, "plan", fake_plan)
    monkeypatch.setattr(intake_service_module.patient_assistant, "answer", fake_answer)
    monkeypatch.setattr(intake_service_module.answer_guard, "check", fake_answer_review)


class RejectingHMS:
    """`verify_credentials` always fails - lets a test drive the 401 path without needing a
    second, deliberately-wrong OpenEMR account."""

    def verify_credentials(self, username: str, password: str):
        return None


def new_consented_session(client) -> tuple[str, str]:
    s = client.post(f"{BASE}/intake-sessions", json={}).json()
    client.post(f"{BASE}/intake-sessions/{s['session_id']}/consent", json={"granted": True})
    return s["session_id"], s["case_id"]


def new_identified_session(client) -> tuple[str, str]:
    """Consent + identity form. Registers (or updates) a patient in the hospital system."""
    sid, cid = new_consented_session(client)
    res = client.post(f"{BASE}/intake-sessions/{sid}/identity", json=IDENTITY_FORM)
    assert res.status_code == 200, res.text
    return sid, cid


def skip_required_attachments(client, case_id: str) -> None:
    """The demo hospital requires lab_report + prescription before intake can complete."""
    for kind in ("lab_report", "prescription"):
        client.post(f"{BASE}/cases/{case_id}/attachments/skip", json={"kind": kind})


def answer_clinical_questions(client, session_id: str, opening: str = "knee pain for about a week") -> dict[str, Any]:
    """Deny every clinical question after the opening statement; returns the closing turn."""
    last: dict[str, Any] = {}
    for message in (opening, "no", "no", "no", "no", "no"):
        last = client.post(f"{BASE}/intake-sessions/{session_id}/messages", json={"content": message}).json()
    return last


def wait_for_status(client, case_id: str, status: str, timeout_s: float = 60.0) -> dict[str, Any]:
    """Poll the case until the background workflow lands it at `status`; returns the detail.
    Generous timeout: prescreen talks to the hospital system on the way through."""
    deadline = time.monotonic() + timeout_s
    while True:
        detail = client.get(f"{BASE}/cases/{case_id}").json()
        if detail["status"] == status:
            return detail
        if time.monotonic() > deadline:
            raise AssertionError(f"case {case_id} is {detail['status']}, expected {status}")
        time.sleep(0.2)


def require_attachments(monkeypatch, *kinds: str) -> set[str]:
    """Make the clinic require these attachment kinds for the duration of one test.

    The demo clinic requires none - attaching is offered, never chased - so a test covering
    the requirement gate has to state the requirement itself rather than lean on clinic
    policy, which is configuration and free to change.
    """
    monkeypatch.setattr("app.services.hospital_config.required_attachment_kinds", lambda: list(kinds))
    return set(kinds)
