"""Safety / Urgency Evaluator — the authoritative priority decision.

**This agent makes zero LLM calls, by design.** It reads approved TriageRule
rows, hands them to the pure rule engine, and persists exactly what comes back.
No prompt, no model output, and no uploaded document can reach a priority
through this path.
"""

from sqlalchemy.orm import Session

from agents.question_planner import DECLINED, NONE_REPORTED, NOT_CAPTURED
from models import AllergyMedication, AuditEvent, PatientFact, TriageResult, TriageRule
from services import hospital_config, triage_engine

# What intake writes when a field was closed without a clinical value: a
# denial, a decline, or a reply the extractor made nothing of. They are stored
# as ordinary rows so the field reads as answered, which means they arrive here
# looking exactly like a substance name.
PLACEHOLDER_NAMES = frozenset({NONE_REPORTED, DECLINED, NOT_CAPTURED})


def clinical_entries(entries: list) -> list:
    """Drop intake's placeholder answers before anything is decided on them.

    The allergy/medication conflict check is a name-overlap test, so a
    placeholder left in matches *itself*: a patient whose allergy answer and
    medication answer were both filed as "Answered — see the intake transcript"
    would be escalated for a conflict between two sentences. The row still
    belongs in the record — it is what tells the clinician the question was
    asked — it just is not a substance, and only substances can conflict.
    """
    return [entry for entry in entries if (entry.name or "").strip() not in PLACEHOLDER_NAMES]


def evaluate_urgency(db: Session, case_id) -> TriageResult:
    facts = db.query(PatientFact).filter(PatientFact.case_id == case_id).all()
    entries = clinical_entries(
        db.query(AllergyMedication).filter(AllergyMedication.case_id == case_id).all()
    )
    # Scoped to the active hospital: another clinic's rules are in the same
    # table and must never fire on this case.
    hospital_id = hospital_config.active_id()
    rules = (
        db.query(TriageRule)
        .filter(TriageRule.hospital_id == hospital_id, TriageRule.retired.is_(False))
        .all()
    )

    if not rules:
        raise RuntimeError(
            f"No triage rules are seeded for hospital '{hospital_id}'. Run "
            "`python scripts/seed.py` or re-activate it from the hospital page — "
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
