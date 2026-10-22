"""Reconcile a clinic's YAML rules into `triage_rules` so results reference real rows."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import TriageRule
from app.services import hospital_config


def sync(db: Session, hospital_id: str | None = None) -> int:
    hospital_id = hospital_id or hospital_config.active_id()
    config = hospital_config.read(hospital_id)
    hospital_config.validate(config)

    block = config.get("triage_rules") or {}
    version = str(block.get("version", "0"))
    entries = block.get("rules") or []

    existing = {
        r.code: r for r in db.query(TriageRule).filter(TriageRule.hospital_id == hospital_id).all()
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
        rule.emergency = bool(entry.get("emergency", False))
        rule.retired = False
    for stale in existing.values():
        stale.retired = True

    db.commit()
    return len(entries)


def active_rules(db: Session, hospital_id: str) -> list[TriageRule]:
    return (
        db.query(TriageRule)
        .filter(TriageRule.hospital_id == hospital_id, TriageRule.retired.is_(False))
        .all()
    )