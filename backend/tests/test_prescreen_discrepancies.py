"""check_discrepancies runs inside the prescreen workflow but must never change what
evaluate_urgency computes. Needs Postgres from .env."""

import time
import uuid

import pytest
from fastapi.testclient import TestClient

from app.db import db_session
from app.domain import triage_engine
from app.main import app
from app.services import case_repo, triage_rules
from tests.helpers import BASE, new_identified_session, patch_intake_agents, skip_required_attachments

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def fake_llm(monkeypatch):
    patch_intake_agents(monkeypatch)


def _prescreened_case(client) -> dict:
    """Complete intake and wait for the background prescreen it triggers to land at
    NEEDS_REVIEW; returns the case detail."""
    sid, cid = new_identified_session(client)
    skip_required_attachments(client, cid)
    for msg in ["knee pain for about a week", "no", "no", "no", "no", "no"]:
        last = client.post(f"{BASE}/intake-sessions/{sid}/messages", json={"content": msg}).json()
    assert last["intake_complete"] is True
    for _ in range(100):
        detail = client.get(f"{BASE}/cases/{cid}").json()
        if detail["status"] == "NEEDS_REVIEW":
            return detail
        time.sleep(0.1)
    raise AssertionError(f"prescreen did not complete: status={detail['status']}")


def test_check_discrepancies_step_runs_and_writes_audit_event(client):
    detail = _prescreened_case(client)
    assert isinstance(detail["discrepancies"], list)

    audit_events = client.get(f"{BASE}/cases/{detail['case_id']}/audit").json()
    checked = [e for e in audit_events if e["action"] == "discrepancy.checked"]
    assert len(checked) == 1
    assert {"count", "generated_by"} <= set(checked[0]["payload"])


def test_triage_outcome_is_identical_whether_or_not_discrepancies_exist(client):
    """evaluate_urgency's inputs and output must be unaffected by the discrepancy checker."""
    detail = _prescreened_case(client)
    cid, api_triage = detail["case_id"], detail["triage"]

    with db_session() as db:
        case = case_repo.case_or_404(db, uuid.UUID(cid))
        independent = triage_engine.evaluate(
            case_repo.facts(db, case.id),
            case_repo.clinical_entries(db, case.id),
            triage_rules.active_rules(db, case.hospital_id),
        )

    assert api_triage["priority"] == independent.priority
    assert api_triage["rule_codes"] == independent.rule_codes
    assert api_triage["evidence"] == independent.evidence
