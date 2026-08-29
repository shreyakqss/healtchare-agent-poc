"""The reviewed-intake payload never carries intake sentinels to the HMS."""

from types import SimpleNamespace

from app.domain.intake_fields import DECLINED, NONE_REPORTED, NOT_CAPTURED
from app.services.hms.intake_sync import clinical_entries, clinical_facts


def _fact(kind, value, source="patient"):
    return SimpleNamespace(kind=kind, value=value, source=source)


def _entry(kind, name, source="patient", reaction_or_dose=None):
    return SimpleNamespace(kind=kind, name=name, source=source, reaction_or_dose=reaction_or_dose)


def test_sentinel_facts_are_dropped_but_real_statements_kept():
    facts = [_fact("history", "asthma"), _fact("history", NONE_REPORTED), _fact("symptom", DECLINED), _fact("duration", NOT_CAPTURED)]
    assert clinical_facts(facts) == [{"kind": "history", "value": "asthma", "source": "patient"}]


def test_sentinel_entries_are_dropped_and_provenance_travels():
    entries = [_entry("allergy", NONE_REPORTED), _entry("medication", "inhaler", source="hms", reaction_or_dose="2 puffs")]
    assert clinical_entries(entries) == [
        {"kind": "medication", "name": "inhaler", "reaction_or_dose": "2 puffs", "source": "hms"}
    ]
