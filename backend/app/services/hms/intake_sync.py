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


def reviewed_payload(db: Session, case: PatientCase) -> dict[str, Any]:
    session = case_repo.session_for(db, case)
    triage = case_repo.latest_triage(db, case.id)
    routing = case_repo.latest_routing(db, case.id)
    return {
        "case_id": str(case.id),
        "transcript": [
            {"role": m.role, "content": m.content, "turn_index": m.turn_index}
            for m in case_repo.messages(db, session.id)
        ],
        "facts": clinical_facts(case_repo.facts(db, case.id)),
        "entries": clinical_entries(case_repo.entries(db, case.id)),
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
            for n in case_repo.notes(db, case.id)
        ],
    }
