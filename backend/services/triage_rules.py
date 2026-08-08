"""Sync the active hospital's YAML rules into the `triage_rules` table.

They live in the DB so `TriageResult.rule_ids` points at real rows and the audit
trail can resolve which rule fired; they are authored in YAML so a non-developer
can read and edit them. This function is the one place that reconciles the two,
called by `scripts/seed.py` at setup and by the hospital API whenever a config
is saved or a different clinic is activated.
"""

from sqlalchemy.orm import Session

from models import TriageRule
from services import hospital_config


def sync(db: Session, hospital_id: str | None = None) -> int:
    """Upsert one hospital's rules, keyed on (hospital_id, code).

    Rules dropped from the YAML are retired rather than deleted, and only for
    this hospital — other clinics' rows are untouched. Nothing here ever removes
    a row a `TriageResult.rule_ids` might still point at.
    """
    hospital_id = hospital_id or hospital_config.active_id()
    config = hospital_config.read(hospital_id)
    hospital_config.validate(config)

    block = config.get("triage_rules") or {}
    version = str(block.get("version", "0"))
    entries = block.get("rules") or []

    existing = {
        rule.code: rule
        for rule in db.query(TriageRule)
        .filter(TriageRule.hospital_id == hospital_id)
        .all()
    }

    for entry in entries:
        rule = existing.pop(entry["code"], None)
        if rule is None:
            rule = TriageRule(hospital_id=hospital_id, code=entry["code"])
            db.add(rule)
        rule.version = version
        rule.priority = entry["priority"]
        rule.condition = entry.get("condition") or {}
        rule.action = entry["action"]
        rule.explanation = entry["explanation"]
        rule.specialty_hint = entry.get("specialty_hint")
        rule.retired = False  # a code can come back after being removed

    # Whatever is left in `existing` was removed from the YAML.
    for stale in existing.values():
        stale.retired = True

    db.commit()
    return len(entries)
