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
    "reason_for_visit": "why they are seeking care today",
    "symptom": "what symptoms they are experiencing",
    "duration": "how long the symptoms have lasted",
    "name": "their full name",
    "age": "their age",
    "gender": "their gender",
    "history": "relevant past medical conditions",
    "medication": "any medications they currently take",
    "allergy": "any allergies they have",
    "contact_preference": "how they prefer to be contacted",
}

_DENIAL_OPENERS = ("no", "nope", "nah", "none", "nothing", "negative", "n/a", "nil")
_DENIAL_PHRASES = (
    "don't have any", "do not have any", "dont have any", "no known", "none at all",
    "not that i know", "nothing like that", "never had", "no history",
)
_MOVE_ON = (
    "repeating", "repeat", "already asked", "already told", "already answered",
    "asked me that", "same question", "move on", "next step", "go ahead",
    "stop asking", "skip this", "skip",
)
_EMPTY_ANSWERS = {"no", "none", "nope", "nothing", "nil", "n/a", "na", "-", "n"}


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


def is_denial(message: str) -> bool:
    lowered = message.strip().lower()
    first = lowered.replace(",", " ").replace(".", " ").split()
    if first and first[0] in _DENIAL_OPENERS:
        return True
    return any(p in lowered for p in _DENIAL_PHRASES)


def wants_to_move_on(message: str) -> bool:
    lowered = message.lower()
    return any(s in lowered for s in _MOVE_ON)


def is_empty_answer(value: str) -> bool:
    return value.strip().strip(".,!").lower() in _EMPTY_ANSWERS


def settle_value(reply: str) -> str:
    """How to close a field the patient answered without producing a fact."""
    if wants_to_move_on(reply):
        return DECLINED
    if is_denial(reply):
        return NONE_REPORTED
    return NOT_CAPTURED