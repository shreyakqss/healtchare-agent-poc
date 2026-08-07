"""Create the schema and seed the demo.

    python scripts/seed.py            # create tables + seed rules and cases
    python scripts/seed.py --reset    # drop everything first (repeatable demo)
    python scripts/seed.py --rules-only

Run from the `backend/` directory with the AI-POC venv active.

There is no Alembic in Phase 1 — the schema is created directly from the models,
which is why --reset is the supported way to pick up a model change.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

# Running `python scripts/seed.py` puts scripts/ on sys.path, not backend/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import settings  # noqa: E402
from models import Base, SessionLocal, TriageRule, engine  # noqa: E402
from services import hospital_config  # noqa: E402


def reset_schema() -> None:
    print("Dropping all tables...")
    Base.metadata.drop_all(engine)

    upload_dir = Path(settings.UPLOAD_DIR)
    if upload_dir.exists():
        print(f"Clearing uploads at {upload_dir}...")
        shutil.rmtree(upload_dir, ignore_errors=True)


def create_schema() -> None:
    print("Creating tables...")
    Base.metadata.create_all(engine)
    Path(settings.UPLOAD_DIR).mkdir(parents=True, exist_ok=True)


def seed_triage_rules(db) -> int:
    """Load approved rules from hospital.yaml into the database.

    They live in the DB so TriageResult.rule_ids points at real rows and the
    audit trail can resolve which rule fired; they are authored in YAML so a
    non-developer can read and edit them.
    """
    config = hospital_config.reload()
    block = config.get("triage_rules", {})
    version = str(block.get("version", "0"))
    rules = block.get("rules", [])

    if not rules:
        raise SystemExit(
            "hospital.yaml defines no triage rules. A priority must always trace "
            "to a configured rule, so refusing to seed an empty rule set."
        )
    if not any(not (r.get("condition") or {}) for r in rules):
        raise SystemExit(
            "hospital.yaml has no fallback rule (one with an empty condition). "
            "Without it a case could get no priority at all."
        )

    existing = {r.code: r for r in db.query(TriageRule).all()}
    written = 0

    for entry in rules:
        rule = existing.get(entry["code"])
        if rule is None:
            rule = TriageRule(code=entry["code"])
            db.add(rule)
        rule.version = version
        rule.priority = entry["priority"]
        rule.condition = entry.get("condition") or {}
        rule.action = entry["action"]
        rule.explanation = entry["explanation"]
        rule.specialty_hint = entry.get("specialty_hint")
        written += 1

    db.commit()
    return written


def seed_cases(db) -> int:
    from scripts.generate_synthetic import generate_all

    cases = generate_all(db)
    return len(cases)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Drop all tables and uploaded files before seeding.",
    )
    parser.add_argument(
        "--rules-only",
        action="store_true",
        help="Seed triage rules but skip the synthetic patient cases.",
    )
    args = parser.parse_args()

    if args.reset:
        reset_schema()
    create_schema()

    db = SessionLocal()
    try:
        rule_count = seed_triage_rules(db)
        print(f"Seeded {rule_count} triage rules "
              f"(version {hospital_config.triage_rules().get('version')}).")

        if args.rules_only:
            print("Skipping synthetic cases (--rules-only).")
        else:
            case_count = seed_cases(db)
            print(f"Seeded {case_count} synthetic patient cases.")
    finally:
        db.close()

    # ASCII only: the Windows console defaults to cp1252 and mangles anything else.
    print("\nDone. Synthetic data only - no real patient information.")
    print("Start the API with:  uvicorn main:app --reload")


if __name__ == "__main__":
    main()
