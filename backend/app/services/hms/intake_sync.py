"""The clinician-approved intake payload handed to `HMSClient.sync_reviewed_intake`.

Assembled only at finalisation, after a `ClinicalReview` with approve/edit exists and
consultation notes are recorded. Provenance (`source`) travels with every row so the
adapter can write patient statements and skip HMS imports.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Protocol

from sqlalchemy.orm import Session

from app.domain.intake_fields import PLACEHOLDERS
from app.models import PatientCase
from app.services import case_repo


class _Fact(Protocol):
    kind: str
    value: str
    source: str


class _Entry(Protocol):
    kind: str
    name: str
    reaction_or_dose: str | None
    source: str


def clinical_facts(facts: Iterable[_Fact]) -> list[dict[str, Any]]:
    """Fact rows worth writing to a chart: the intake sentinels ("None reported by patient",
    "Declined to answer", ...) close a question, they are not clinical statements."""
    return [
        {"kind": f.kind, "value": f.value, "source": f.source}
        for f in facts if f.value not in PLACEHOLDERS
    ]


def clinical_entries(entries: Iterable[_Entry]) -> list[dict[str, Any]]:
    return [
        {"kind": e.kind, "name": e.name, "reaction_or_dose": e.reaction_or_dose, "source": e.source}
        for e in entries if e.name not in PLACEHOLDERS
    ]


# The signed OPD record's clinical headings (frontend consultation-form NOTE_HEADINGS).
PAST_HISTORY = "Past history:"
_NEXT_HEADINGS = ("Current medications:", "Examination:", "Allergies:", "Presenting complaints:", "History of presenting illness:")
_NIL = {"nil", "nil significant", "none", "nkda", "no significant past history", "not significant"}


def signed_problems(notes_text: str) -> list[str]:
    """The conditions the doctor signed under Past history - the only text that goes on the
    hospital chart's problem list, so 'last period 2 weeks ago' or 'finished nitrofurantoin'
    (patient history facts, not diagnoses) never become medical problems."""
    start = notes_text.find(PAST_HISTORY)
    if start < 0:
        return []
    body = notes_text[start + len(PAST_HISTORY):]
    ends = [i for i in (body.find(h) for h in _NEXT_HEADINGS) if i >= 0]
    body = body[: min(ends)] if ends else body
    lines = [line.strip().rstrip(".") for line in body.splitlines()]
    return [line for line in lines if line and line.lower() not in _NIL]


def reviewed_payload(db: Session, case: PatientCase) -> dict[str, Any]:
    session = case_repo.session_for(db, case)
    triage = case_repo.latest_triage(db, case.id)
    routing = case_repo.latest_routing(db, case.id)
    notes = case_repo.notes(db, case.id)
    return {
        "case_id": str(case.id),
        "transcript": [
            {"role": m.role, "content": m.content, "turn_index": m.turn_index}
            for m in case_repo.messages(db, session.id)
        ],
        "facts": clinical_facts(case_repo.facts(db, case.id)),
        "entries": clinical_entries(case_repo.entries(db, case.id)),
        "problems": signed_problems(notes[-1].notes) if notes else [],
        "triage": (
            {"priority": triage.priority, "rule_codes": triage.rule_codes, "evidence": triage.evidence}
            if triage else None
        ),
        "routing": (
            {"department": routing.department_name, "appointment_type": routing.appointment_type_label}
            if routing else None
        ),
        "consultation_notes": [
            {"notes": n.notes, "prescription": n.prescription, "follow_up_instructions": n.follow_up_instructions}
            for n in notes[-1:]  # the latest version is the signed report
        ],
    }
