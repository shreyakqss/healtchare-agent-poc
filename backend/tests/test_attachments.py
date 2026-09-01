"""Required-attachment-before-prescreen, with a skip option (needs Postgres from .env)."""

import io
import time
import uuid

import pytest
from fastapi.testclient import TestClient

from app.db import db_session
from app.main import app
from app.services import case_repo
from tests.helpers import BASE, new_identified_session, patch_intake_agents, require_attachments

pytestmark = pytest.mark.integration

# What these tests make the clinic require, per test, via `require_attachments`. The demo
# hospital itself requires nothing - attaching is offered from the composer, never chased -
# so the gate has to be asked for explicitly rather than inherited from configuration.
REQUIRED_KINDS = ("lab_report", "prescription")


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def fake_llm(monkeypatch):
    patch_intake_agents(monkeypatch)


def _complete_chat(client, sid: str) -> dict:
    """Answers every clinical question with a denial - fast, deterministic, no real facts."""
    last = {}
    for msg in ["annual checkup", "no", "no", "no", "no", "no"]:
        last = client.post(f"{BASE}/intake-sessions/{sid}/messages", json={"content": msg}).json()
    return last


def _upload(client, case_id: str, kind: str) -> dict:
    files = {"file": ("report.txt", io.BytesIO(b"synthetic report text"), "text/plain")}
    res = client.post(f"{BASE}/cases/{case_id}/attachments", files=files, data={"kind": kind, "uploaded_by": "patient"})
    assert res.status_code == 201, res.text
    return res.json()


def _skip(client, case_id: str, kind: str, reason: str | None = None) -> dict:
    body = {"kind": kind, **({"reason": reason} if reason is not None else {})}
    res = client.post(f"{BASE}/cases/{case_id}/attachments/skip", json=body)
    assert res.status_code == 200, res.text
    return res.json()


def test_skip_endpoint_writes_audit_event(client):
    _, cid = new_identified_session(client)
    assert _skip(client, cid, "lab_report", reason="Don't have a printer here") == {"ok": True}

    audit_events = client.get(f"{BASE}/cases/{cid}/audit").json()
    skipped = [e for e in audit_events if e["action"] == "attachment.skipped"]
    assert len(skipped) == 1
    assert skipped[0]["payload"] == {"kind": "lab_report", "reason": "Don't have a printer here"}


def test_skip_endpoint_rejects_unknown_kind(client):
    _, cid = new_identified_session(client)
    assert client.post(f"{BASE}/cases/{cid}/attachments/skip", json={"kind": "not_a_real_kind"}).status_code == 422


def test_chat_completion_leaves_prescreen_unfired_with_pending_attachments(client, monkeypatch):
    require_attachments(monkeypatch, *REQUIRED_KINDS)
    fired: list[str] = []

    async def fake_run_prescreen(case_id, **_) -> None:
        fired.append(str(case_id))

    monkeypatch.setattr("app.services.workflow_jobs.run_prescreen", fake_run_prescreen)

    sid, _ = new_identified_session(client)
    assert _complete_chat(client, sid)["intake_complete"] is True

    time.sleep(0.3)
    assert fired == []

    session = client.get(f"{BASE}/intake-sessions/{sid}").json()
    assert set(REQUIRED_KINDS) <= set(session["pending_attachment_kinds"])


def test_upload_push_to_hms_retries_then_writes_failure_audit_event(client, monkeypatch):
    """A transient push_document failure is retried once; on final failure an audit event
    surfaces the gap instead of leaving hms_reference silently None."""
    _, cid = new_identified_session(client)
    calls = {"n": 0}

    class _AlwaysFailingHMS:
        def push_document(self, mrn, title, content, content_type="text/plain"):
            calls["n"] += 1
            raise ConnectionError("simulated transient failure")

    monkeypatch.setattr("app.services.attachment_service.get_hms", lambda: _AlwaysFailingHMS())
    monkeypatch.setattr("app.services.hms.documents.time.sleep", lambda s: None)

    result = _upload(client, cid, "lab_report")
    assert calls["n"] == 2

    with db_session() as db:
        row = case_repo.attachments(db, uuid.UUID(cid))[0]
        assert row.hms_reference is None
        assert str(row.id) == result["id"]

    audit_events = client.get(f"{BASE}/cases/{cid}/audit").json()
    failed = [e for e in audit_events if e["action"] == "attachment.push_to_hms_failed"]
    assert len(failed) == 1
    assert failed[0]["payload"]["error_type"] == "ConnectionError"


def test_upload_pushes_to_linked_hms_record(client):
    """Under the mock provider the identity step links every case to an HMS record, so an
    upload is forwarded and its reference stored on the row."""
    _, cid = new_identified_session(client)
    _upload(client, cid, "lab_report")
    with db_session() as db:
        row = case_repo.attachments(db, uuid.UUID(cid))[0]
        assert row.hms_reference
    audit_events = client.get(f"{BASE}/cases/{cid}/audit").json()
    assert any(e["action"] == "attachment.pushed_to_hms" for e in audit_events)


def test_prescription_upload_extracts_medication_candidates_without_creating_entries(client, monkeypatch):
    """Candidates are surfaced for the patient to confirm, never written as AllergyMedication
    rows directly - see CLAUDE.md: uploaded document text may ground an answer, never become a fact."""
    from app.agents.schemas import MedicationCandidatesResult

    async def fake_extract_medications(text: str) -> MedicationCandidatesResult:
        return MedicationCandidatesResult(medications=["Metformin", "Atorvastatin"])

    monkeypatch.setattr("app.services.attachment_service.extract_medications", fake_extract_medications)

    _, cid = new_identified_session(client)
    _upload(client, cid, "prescription")

    with db_session() as db:
        row = case_repo.attachments(db, uuid.UUID(cid))[0]
        assert row.extracted_medications == ["Metformin", "Atorvastatin"]
        assert case_repo.entries(db, uuid.UUID(cid)) == []
        assert case_repo.pending_medication_candidates(db, uuid.UUID(cid)) == ["Metformin", "Atorvastatin"]


def test_document_resolved_after_chat_closed_fires_prescreen(client, monkeypatch):
    require_attachments(monkeypatch, *REQUIRED_KINDS)
    """The chat can close while a required document is still pending; resolving it later
    from the patient page must start pre-screening - not leave the case stuck in intake."""
    fired: list[str] = []

    async def fake_run_prescreen(case_id, **_) -> None:
        fired.append(str(case_id))

    monkeypatch.setattr("app.services.workflow_jobs.run_prescreen", fake_run_prescreen)

    sid, cid = new_identified_session(client)
    _skip(client, cid, "lab_report")
    assert _complete_chat(client, sid)["intake_complete"] is True
    time.sleep(0.2)
    assert fired == []  # prescription still pending

    _skip(client, cid, "prescription")
    for _ in range(20):
        if fired:
            break
        time.sleep(0.1)
    assert fired == [cid]

    _skip(client, cid, "prescription")  # resolving again must not fire a second run
    time.sleep(0.2)
    assert fired == [cid]


def test_chat_completion_fires_prescreen_with_mix_of_upload_and_skip(client, monkeypatch):
    require_attachments(monkeypatch, *REQUIRED_KINDS)
    fired: list[str] = []

    async def fake_run_prescreen(case_id, **_) -> None:
        fired.append(str(case_id))

    monkeypatch.setattr("app.services.workflow_jobs.run_prescreen", fake_run_prescreen)

    sid, cid = new_identified_session(client)
    _upload(client, cid, "lab_report")
    _skip(client, cid, "prescription", reason="No prescriptions to bring")
    assert _complete_chat(client, sid)["intake_complete"] is True

    for _ in range(20):
        if fired:
            break
        time.sleep(0.1)
    assert fired == [cid]

    detail = client.get(f"{BASE}/cases/{cid}").json()
    assert set(REQUIRED_KINDS) <= set(detail["required_attachment_kinds"])
    assert detail["pending_attachment_kinds"] == []
