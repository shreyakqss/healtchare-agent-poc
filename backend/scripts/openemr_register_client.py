"""Register CareFlow as an OAuth2 client on an OpenEMR instance (RFC 7591 dynamic registration).

    python scripts/openemr_register_client.py --base-url http://localhost:8300 --out client.json

OpenEMR fixes a client's scopes at registration time (the admin UI shows them read-only),
so the scope list below is the complete set the adapter needs: FHIR resources for reads,
standard-API resources for writes. After running:

  1. OpenEMR -> Administration -> System -> API Clients: open the new "CareFlow" client and
     click "Enable Client" (dynamically registered clients start disabled).
  2. Copy client_id / client_secret from the output file into backend/.env as
     OPENEMR_CLIENT_ID / OPENEMR_CLIENT_SECRET, and the printed scope string as OPENEMR_SCOPES.
  3. Restart the CareFlow backend; GET /health must report hms.connected=true.

The secret is printed once by OpenEMR and never again - keep the output file out of git.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.integrations.hms.openemr.scopes import DEFAULT_SCOPES  # noqa: E402

_REJECTED_SCOPE = re.compile(r"Check the `([^`]+)` scope")


def register(base_url: str, name: str, scopes: str) -> tuple[dict, list[str]]:
    """Register the client, dropping any scope this OpenEMR does not recognise.

    Installs differ in what they offer (8.3.0 rejects `user/MedicationStatement.read`, for
    instance) and the whole registration fails on the first unknown one, naming it. Rather
    than make the operator bisect the list by hand, retry without it and report what went.
    Returns `(registration, dropped_scopes)`.
    """
    wanted = scopes.split()
    dropped: list[str] = []
    for _ in range(len(wanted)):
        body = {
            "application_type": "private",
            "client_name": name,
            "token_endpoint_auth_method": "client_secret_post",
            "contacts": ["careflow@example.test"],
            "scope": " ".join(wanted),
            # OpenEMR requires at least one redirect URI even for a confidential, grant-only client.
            "redirect_uris": [f"{base_url.rstrip('/')}/careflow/callback"],
        }
        resp = httpx.post(f"{base_url.rstrip('/')}/oauth2/default/registration", json=body, timeout=30)
        if resp.is_success:
            return resp.json(), dropped
        match = _REJECTED_SCOPE.search(resp.text.replace("\\/", "/"))
        if not match:
            resp.raise_for_status()
        rejected = match.group(1)
        dropped.append(rejected)
        wanted.remove(rejected)
    raise RuntimeError("OpenEMR rejected every requested scope")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-url", default="http://localhost:8300")
    parser.add_argument("--name", default="CareFlow")
    parser.add_argument("--scopes", default=DEFAULT_SCOPES, help="space-separated; defaults to the adapter's full list")
    parser.add_argument("--out", type=Path, required=True, help="where to write the registration response (contains the secret)")
    args = parser.parse_args()

    registration, dropped = register(args.base_url, args.name, args.scopes)
    args.out.write_text(json.dumps(registration, indent=2), encoding="utf-8")
    print(f"Registered client_id={registration.get('client_id')}")
    if dropped:
        print(f"This OpenEMR does not offer these scopes, so they were dropped: {' '.join(dropped)}")
    print(f"Secret and full response written to {args.out} (do not commit).")
    print("Now enable the client in OpenEMR: Administration -> System -> API Clients -> edit -> Enable Client.")
    print(f"OPENEMR_SCOPES={registration.get('scope', args.scopes)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
