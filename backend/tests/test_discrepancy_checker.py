"""Discrepancy checker agent: AgentUnavailable fallback + structured-output parsing.

No network calls - `run_structured` is exercised directly against a fake agent, the same
way `AgentUnavailable` propagates for any agno agent module in this repo. No pytest-asyncio
in this project's venv, so async calls run via asyncio.run().
"""

from __future__ import annotations

import asyncio

import pytest

import app.agents.llm as llm_module
from app.agents import AgentUnavailable
from app.agents.llm import run_structured
from app.agents.schemas import Discrepancy, DiscrepancyResult


class _FakeResult:
    def __init__(self, content):
        self.content = content


class _FakeAgent:
    name = "Discrepancy Checker"

    def __init__(self, content):
        self._content = content

    async def arun(self, prompt: str):
        return _FakeResult(self._content)


def test_agent_unavailable_when_no_llm_key(monkeypatch):
    monkeypatch.setattr(llm_module, "llm_available", lambda: False)
    with pytest.raises(AgentUnavailable):
        asyncio.run(run_structured(_FakeAgent({}), "prompt", DiscrepancyResult))


def test_structured_output_parses_into_discrepancy_result(monkeypatch):
    monkeypatch.setattr(llm_module, "llm_available", lambda: True)
    payload = {
        "discrepancies": [
            {
                "field_or_topic": "medications",
                "patient_stated": "no medications",
                "document_or_hms_says": "Metformin 500mg listed in referral letter",
                "source_kind": "document",
                "attachment_id": "11111111-1111-1111-1111-111111111111",
                "severity": "review",
                "requested_document_kind": "prescription",
            }
        ]
    }
    result = asyncio.run(run_structured(_FakeAgent(payload), "prompt", DiscrepancyResult))
    assert isinstance(result, DiscrepancyResult)
    assert len(result.discrepancies) == 1
    d = result.discrepancies[0]
    assert isinstance(d, Discrepancy)
    assert d.field_or_topic == "medications"
    assert d.source_kind == "document"
    assert d.severity == "review"
    assert d.requested_document_kind == "prescription"


def test_structured_output_defaults_to_empty_list(monkeypatch):
    monkeypatch.setattr(llm_module, "llm_available", lambda: True)
    result = asyncio.run(run_structured(_FakeAgent({"discrepancies": []}), "prompt", DiscrepancyResult))
    assert result.discrepancies == []


def test_discrepancy_result_empty_never_raises():
    """The workflow's fallback shape - what check_discrepancies persists when the agent is unavailable."""
    result = DiscrepancyResult(discrepancies=[])
    assert result.discrepancies == []
