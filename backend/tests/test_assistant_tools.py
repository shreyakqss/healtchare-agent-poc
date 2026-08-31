import asyncio
import json
import uuid
from types import SimpleNamespace

from app.services import assistant_tools


def test_general_health_lookup_receives_only_the_generalized_topic(monkeypatch):
    calls = []

    async def search(topic: str) -> str:
        calls.append(topic)
        return '{"topic":"metformin uses","results":[]}'

    def private_data_access(*_):
        raise AssertionError("general health lookup must not read the patient's case")

    monkeypatch.setattr(assistant_tools.settings, "TAVILY_API_KEY", "test-key")
    monkeypatch.setattr(assistant_tools, "search_health_information", search)
    monkeypatch.setattr(assistant_tools.case_repo, "attachments", private_data_access)
    monkeypatch.setattr(assistant_tools.case_repo, "facts", private_data_access)
    monkeypatch.setattr(assistant_tools.case_repo, "clinical_entries", private_data_access)

    result = asyncio.run(assistant_tools.resolve(None, uuid.uuid4(), "general_health", "metformin uses"))

    assert calls == ["metformin uses"]
    assert json.loads(result)["topic"] == "metformin uses"


def test_personal_record_never_calls_external_search(monkeypatch):
    async def external_search(_):
        raise AssertionError("personal record questions must not reach external search")

    monkeypatch.setattr(assistant_tools, "search_health_information", external_search)
    monkeypatch.setattr(
        assistant_tools.case_repo,
        "attachments",
        lambda *_: [SimpleNamespace(kind="prescription", filename="rx.txt", extracted_text="metformin 500 mg")],
    )
    monkeypatch.setattr(
        assistant_tools.case_repo,
        "facts",
        lambda *_: [
            SimpleNamespace(kind="name", value="Private Name"),
            SimpleNamespace(kind="symptom", value="headache"),
        ],
    )
    monkeypatch.setattr(
        assistant_tools.case_repo,
        "clinical_entries",
        lambda *_: [SimpleNamespace(kind="medication", name="metformin", reaction_or_dose="500 mg")],
    )

    result = json.loads(asyncio.run(assistant_tools.resolve(None, uuid.uuid4(), "personal_record")))

    assert result["documents"][0]["text"] == "metformin 500 mg"
    assert result["intake"] == [{"kind": "symptom", "value": "headache"}]
    assert "Private Name" not in json.dumps(result)
