"""Safety / Urgency Evaluator — the authoritative priority decision.

**This agent makes zero LLM calls, by design.** It reads approved TriageRule
rows, hands them to the pure rule engine, and persists exactly what comes back.
No prompt, no model output, and no uploaded document can reach a priority
through this path.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from models import AllergyMedication, AuditEvent, PatientFact, TriageResult, TriageRule
from services import triage_engine


def evaluate_urgency(db: Session, case_id) -> TriageResult:
    facts = db.query(PatientFact).filter(PatientFact.case_id == case_id).all()
    entries = (
        db.query(AllergyMedication)
        .filter(AllergyMedication.case_id == case_id)
        .all()
    )
    rules = db.query(TriageRule).all()

    if not rules:
        raise RuntimeError(
            "No triage rules are seeded. Run `python scripts/seed.py` first — "
            "a priority must always trace to a configured rule."
        )

    outcome = triage_engine.evaluate(facts, entries, rules)

    result = TriageResult(
        case_id=case_id,
        priority=outcome.priority,
        rule_ids=outcome.rule_ids,
        warnings=outcome.warnings,
        evidence=outcome.evidence,
    )
    db.add(result)

    db.add(
        AuditEvent(
            case_id=case_id,
            actor="system:urgency_evaluator",
            action="triage.evaluated",
            payload={
                "priority": outcome.priority,
                "rule_codes": outcome.rule_codes,
                "warning_count": len(outcome.warnings),
                "engine": "rules",  # never "llm"
            },
        )
    )
    db.commit()
    db.refresh(result)

    # Carried on the instance for the graph; not a column.
    result.specialty_hint = outcome.specialty_hint  # type: ignore[attr-defined]
    result.rule_codes = outcome.rule_codes  # type: ignore[attr-defined]
    return result
