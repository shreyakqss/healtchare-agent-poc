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
from models import Base, SessionLocal, engine  # noqa: E402
from services import hospital_config, triage_rules  # noqa: E402


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
    """Load the active hospital's approved rules into the database.

    The reconciliation itself lives in `services/triage_rules.py` so the hospital
    admin API runs the identical path when a config is saved or another clinic
    is activated.
    """
    hospital_config.reload()
    try:
        return triage_rules.sync(db)
    except hospital_config.ConfigError as exc:
        raise SystemExit(f"Refusing to seed: {exc}") from exc


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
