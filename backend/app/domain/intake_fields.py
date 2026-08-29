"""Which required intake fields are still open, and how a non-answer closes one.

The trap: a *denial* produces no fact row ("no allergies" extracts nothing), so
a field would read as never asked and be re-asked forever. Every assistant
question records `asks_field`; the next turn closes it with one of three
sentinels. They are deliberately distinct: a denial is clinical information, a
decline is not, and an unparsed answer is neither.
"""

from __future__ import annotations

import re
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

# Errands, not complaints. Someone here for a repeat prescription or a certificate has no
# symptom to state, so their opening line must not be filed as one.
_ADMIN_REQUESTS = (
    "refill", "repeat prescription", "certificate", "fit note", "sick note", "insurance",
    "test result", "lab result", "report copy", "my records", "referral",
    "routine checkup", "routine check-up", "vaccination", "vaccine",
    "follow-up appointment", "follow up appointment",
)


def is_administrative_request(text: str) -> bool:
    """True when an opening statement is an errand rather than a description of a problem.

    Used only on the fallback path, to decide whether the opening line may also stand as the
    symptom answer. Fails towards *treating it as a complaint*, which is both the common case
    and the safe one: the value stored is the patient's own words either way, and asking a
    patient to describe symptoms they have just described is the failure being avoided.
    """
    lowered = text.strip().lower()
    return any(cue in lowered for cue in _ADMIN_REQUESTS)


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


_COUNT = r"(?:couple(?:\s+of)?|few|several|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|\d+)"
# Longest alternatives first: plain `a` would otherwise win at "a couple of months" and the
# article would be dropped from the phrase the patient actually used.
_NUMBER = rf"(?:(?:a|an)\s+{_COUNT}|{_COUNT}|a|an)"
_UNIT = r"(?:min(?:ute)?s?|hours?|hrs?|days?|weeks?|months?|years?)"
# "since this morning", "since last night", "since yesterday", "since Monday"
_SINCE = re.compile(r"\bsince\s+((?:this|last|early)\s+\w+|yesterday|today|tonight|\w+day)\b", re.I)
# "for three weeks", "about 2 days", "a couple of months". `(?!\s+old)` keeps "34 years old"
# out - that is an age, not a duration.
_QUANTITY = re.compile(rf"\b(?:for|over|about|around|roughly|past|last)?\s*({_NUMBER}\s+{_UNIT})(?!\s+old)\b", re.I)


def extract_duration(text: str) -> str | None:
    """Pull a duration phrase out of free text, in the patient's own words.

    Deterministic backup for the fact extractor: when the LLM is unavailable the whole
    sentence would otherwise be stored as one fact, and the assistant would go on to ask
    "how long has this been going on?" about something the patient already answered.
    Returns None when nothing clearly duration-shaped is present.
    """
    for pattern in (_SINCE, _QUANTITY):
        m = pattern.search(text)
        if m:
            return " ".join(m.group(0).split())
    return None


_QUESTION_OPENERS = (
    "what ", "what's", "who ", "who's", "when ", "where ", "why ", "how ",
    "which ", "can you", "could you", "do you", "will you", "are you", "is it", "does it",
)


def is_off_topic(message: str) -> bool:
    """A reply phrased as a question TO the assistant ("what are the 2026 movies?") is not
    an answer at all - settling a field from it via NOT_CAPTURED would silently mark that
    field satisfied with junk, and every further off-topic message would burn a fact-extractor
    and question-planner call for nothing. Deliberately narrow (interrogative opener only,
    no question-mark requirement - see below): a short or vague reply is still a real answer
    attempt and stays with the extractor/settle_value path, which already handles those cases."""
    lowered = message.strip().lower()
    if not lowered:
        return False
    # No "ends with ?" requirement - plenty of real messages drop the question mark
    # ("what are the 2026 movies") and the opener alone is already a strong enough signal;
    # a genuine answer essentially never starts with one of these words.
    return any(lowered.startswith(o) for o in _QUESTION_OPENERS)


def settle_value(reply: str) -> str:
    """How to close a field the patient answered without producing a fact."""
    if wants_to_move_on(reply):
        return DECLINED
    if is_denial(reply):
        return NONE_REPORTED
    return NOT_CAPTURED