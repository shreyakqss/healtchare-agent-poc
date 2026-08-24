"""Create the schema and seed the demo.

    python scripts/seed.py            # create tables, sync rules, seed demo cases
    python scripts/seed.py --reset    # drop everything first (repeatable demo)
    python scripts/seed.py --rules-only

Run from `backend/` with the venv active. No Alembic: --reset is how a model
change is picked up.
"""

from __future__ import annotations

import argparse
import asyncio
import shutil
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings  # noqa: E402
from app.db import SessionLocal, engine  # noqa: E402
from app.domain.lifecycle import CaseStatus  # noqa: E402
from app.models import (  # noqa: E402
    AllergyMedication,
    Base,
    ClinicalReview,
    ConsultationNote,
    IntakeMessage,
    PatientFact,
)
from app.schemas.requests import StartSessionRequest  # noqa: E402
from app.services import audit, case_repo, hospital_config, intake_service, lifecycle, triage_rules  # noqa: E402
from app.workflows import run_finalize, run_prescreen  # noqa: E402

SEED_FILE = settings.BACKEND_DIR / "data" / "seed" / "cases.yaml" if hasattr(settings, "BACKEND_DIR") else Path(__file__).resolve().parents[1] / "data" / "seed" / "cases.yaml"
STAGES = ["intake", "prescreen", "review", "notes", "finalize"]


def reset_schema() -> None:
    print("Dropping all tables...")
    Base.metadata.drop_all(engine)
    if settings.UPLOAD_DIR.exists():
        shutil.rmtree(settings.UPLOAD_DIR, ignore_errors=True)


def create_schema() -> None:
    print("Creating tables...")
    Base.metadata.create_all(engine)
    settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


async def seed_case(spec: dict) -> str:
    target = STAGES.index(spec.get("stop_at", "prescreen"))
    db = SessionLocal()
    try:
        session, case = intake_service.start_session(
            db, StartSessionRequest(mrn=spec.get("mrn"), demographics=spec.get("demographics", {}))
        )
        intake_service.record_consent(db, session, case, True)

        for idx, (role, content) in enumerate(spec.get("transcript", [])):
            db.add(IntakeMessage(session_id=session.id, role=role, content=content, turn_index=idx))
        for kind, value, turn in spec.get("facts", []):
            db.add(PatientFact(case_id=case.id, kind=kind, value=value, source_turn=turn))
        for kind, name, detail, turn in spec.get("entries", []):
            db.add(AllergyMedication(case_id=case.id, kind=kind, name=name, reaction_or_dose=detail, source_turn=turn))
        audit.record(db, case.id, "system:seed", "intake.seeded", {"facts": len(spec.get("facts", []))})
        db.commit()
        intake_service._sync_demographics(db, case)
        case_id = case.id
    finally:
        db.close()

    if target >= 1:
        await run_prescreen(case_id)
    if target >= 2 and (review := spec.get("review")):
        db = SessionLocal()
        try:
            case = case_repo.case_or_404(db, case_id)
            session = case_repo.session_for(db, case)
            db.add(ClinicalReview(case_id=case_id, decision=review["decision"], reviewer_id=review["reviewer_id"],
                                  reviewer_role=review.get("reviewer_role", "doctor"), edits=review.get("edits", {}), comment=review.get("comment")))
            audit.record(db, case_id, f"doctor:{review['reviewer_id']}", "review.recorded", {"decision": review["decision"], "edited_fields": sorted(review.get("edits", {}))})
            lifecycle.transition(db, session, CaseStatus.APPROVED if review["decision"] != "reject" else CaseStatus.REJECTED, f"doctor:{review['reviewer_id']}", case_id)
        finally:
            db.close()
    if target >= 3 and (note := spec.get("note")):
        db = SessionLocal()
        try:
            db.add(ConsultationNote(case_id=case_id, **note))
            audit.record(db, case_id, f"doctor:{note['doctor_id']}", "consultation.recorded", {"mode": note.get("consultation_mode", "in_person")})
            db.commit()
        finally:
            db.close()
    if target >= 4:
        await run_finalize(case_id)
    return str(case_id)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reset", action="store_true")
    parser.add_argument("--rules-only", action="store_true")
    args = parser.parse_args()

    if args.reset:
        reset_schema()
    create_schema()

    hospital_config.reload()
    db = SessionLocal()
    try:
        count = triage_rules.sync(db)
        print(f"Synced {count} triage rules for '{hospital_config.active_id()}'.")
    finally:
        db.close()

    if not args.rules_only:
        specs = yaml.safe_load(SEED_FILE.read_text(encoding="utf-8"))["cases"]
        for spec in specs:
            case_id = asyncio.run(seed_case(spec))
            print(f"  seeded {spec['key']:<22} -> {spec.get('stop_at', 'prescreen'):<9} {case_id}")
        print(f"Seeded {len(specs)} synthetic cases.")

    print("\nDone. Synthetic data only - no real patient information.")
    print("Start the API with:  uvicorn app.main:app --reload")


if __name__ == "__main__":
    main()