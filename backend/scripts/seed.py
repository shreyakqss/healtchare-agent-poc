"""Migrate the schema and sync the clinic's triage rules.

    python scripts/seed.py            # create tables, sync rules
    python scripts/seed.py --reset    # drop everything first (repeatable demo)

Run from `backend/` with the venv active. `--reset` is destructive and for local demo data only.

There are no seeded demo cases and no synthetic patient registry: patients live in the
hospital system (OpenEMR) and cases are created by going through intake. To get a case for
a demo, run `python scripts/smoke.py` against a running API, or use the patient page.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings  # noqa: E402
from app.db import SessionLocal, engine  # noqa: E402
from app.db.migrations import migrate_database  # noqa: E402
from app.models import Base  # noqa: E402
from app.services import hospital_config, triage_rules  # noqa: E402


def reset_schema() -> None:
    print("Dropping all tables...")
    Base.metadata.drop_all(engine)
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE IF EXISTS alembic_version"))
    if settings.UPLOAD_DIR.exists():
        shutil.rmtree(settings.UPLOAD_DIR, ignore_errors=True)


def migrate_schema() -> None:
    print("Applying migrations...")
    migrate_database()
    settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reset", action="store_true", help="drop every table first")
    args = parser.parse_args()

    if args.reset:
        reset_schema()
    migrate_schema()

    hospital_config.reload()
    db = SessionLocal()
    try:
        count = triage_rules.sync(db)
        print(f"Synced {count} triage rules for '{hospital_config.active_id()}'.")
    finally:
        db.close()

    print("\nDone. Patients and practitioners come from the hospital system, not from here.")
    print("Start the API with:  uvicorn app.main:app --reload")


if __name__ == "__main__":
    main()
