"""Which required intake fields are still open, and how a non-answer closes one.

The trap: a *denial* produces no fact row ("no allergies" extracts nothing), so
a field would read as never asked and be re-asked forever. Every assistant
question records `asks_field`; the next turn closes it with one of three
sentinels. They are deliberately distinct: a denial is clinical information, a
decline is not, and an unparsed answer is neither.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

NONE_REPORTED = "None reported by patient"
DECLINED = "Declined to answer"
NOT_CAPTURED = "Answered - see the intake transcript"
PLACEHOLDERS = frozenset({NONE_REPORTED, DECLINED, NOT_CAPTURED})

ENTRY_FIELDS = {"allergy", "medication"}  # live in allergy_medications, not patient_facts

FIELD_SATISFIED_BY = {
    "reason_for_visit": {"reason_for_visit"},
    "symptom": {"symptom"},
    "duration": {"duration"},
    "history": {"history", "condition"},
    "contact_preference": {"contact_preference"},
    "name": {"name"},
    "age": {"age"},
    "gender": {"gender"},
}

FIELD_PROMPTS = {
    "reason_for_visit": "why you are seeking care today",
    "symptom": "what symptoms you are experiencing",
    "duration": "how long the symptoms have lasted",
    "name": "your full name",
    "age": "your age",
    "gender": "your gender",
    "history": "relevant past medical conditions",
    "medication": "any medications you currently take",
    "allergy": "any allergies you have",
    "contact_preference": "how you prefer to be contacted",
}


class Fact(Protocol):
    kind: str


class Entry(Protocol):
    kind: str


def missing_fields(required: Iterable[str], facts: Iterable[Fact], entries: Iterable[Entry]) -> list[str]:
    present = {f.kind for f in facts}
    entry_kinds = {e.kind for e in entries}
    missing = []
    for field in required:
        if field in ENTRY_FIELDS:
            satisfied = field in entry_kinds
        else:
            satisfied = bool(FIELD_SATISFIED_BY.get(field, {field}) & present)
        if not satisfied:
            missing.append(field)
    return missing


_SENTINEL_FOR_RESPONSE = {
    "answered": NOT_CAPTURED,
    "denied": NONE_REPORTED,
    "declined": DECLINED,
}


def sentinel_for(response: str | None) -> str | None:
    """How a reply that produced no fact closes the field it answered.

    A missing model result or unrelated reply leaves the field open.
    """
    return _SENTINEL_FOR_RESPONSE.get(response or "")
