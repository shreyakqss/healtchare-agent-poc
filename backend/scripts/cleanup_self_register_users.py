"""Delete auto-generated self-register patient accounts and their test cases.

    python scripts/cleanup_self_register_users.py            # dry run - lists what would go
    python scripts/cleanup_self_register_users.py --confirm  # actually deletes

Targets only accounts created by the self-register flow, identified by their placeholder
`@self-register.careflow.local` email - never a real patient's own email (e.g. patient1's).
Deletes the Keycloak user, the local ApplicationUser row, and (via IntakeSession's cascade)
every case, fact, transcript and attachment they own. Run from `backend/` with the venv active.
Prints ASCII only (Windows console is cp1252).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import httpx
from sqlalchemy import delete

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.integrations.keycloak.admin_client import _admin_token  # noqa: E402
from app.models import ApplicationUser, CaseOwner, IntakeSession, PatientCase  # noqa: E402

EMAIL_SUFFIX = "@self-register.careflow.local"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--confirm", action="store_true", help="Actually delete. Without this, only lists what would be removed.")
    args = parser.parse_args()

    with SessionLocal() as db:
        users = db.query(ApplicationUser).filter(ApplicationUser.email.like(f"%{EMAIL_SUFFIX}")).all()
        if not users:
            print("No self-register accounts found.")
            return

        print(f"Found {len(users)} self-register account(s):")
        for u in users:
            print(f"  {u.username}  {u.email}  ({u.id})")
        if not args.confirm:
            print("\nDry run - pass --confirm to delete these accounts and their cases.")
            return

        base = f"{settings.KEYCLOAK_ADMIN_URL.rstrip('/')}/admin/realms/{settings.KEYCLOAK_REALM}"
        headers = {"Authorization": f"Bearer {_admin_token()}"}

        for u in users:
            case_ids = [row.case_id for row in db.query(CaseOwner).filter(CaseOwner.user_id == u.id).all()]
            if case_ids:
                session_ids = [
                    row.session_id for row in db.query(PatientCase).filter(PatientCase.id.in_(case_ids)).all()
                ]
                db.execute(delete(IntakeSession).where(IntakeSession.id.in_(session_ids)))
            db.delete(u)

            resp = httpx.delete(f"{base}/users/{u.subject}", headers=headers, timeout=10.0)
            if resp.status_code not in (204, 404):
                resp.raise_for_status()
            print(f"Deleted {u.username}")

        db.commit()
    print("Done.")


if __name__ == "__main__":
    main()
