# CareFlow: AI-assisted patient intake and administrative triage (POC)

CareFlow is a local clinic proof of concept running against OpenEMR. The assistant collects a patient's story,
approved deterministic rules set an administrative priority, a navigator proposes routing, and nothing is released
to the patient before clinician review.

It does not diagnose, prescribe, handle emergencies, interpret images, or book appointments. Use synthetic test data
only. [Architecture](docs/ARCHITECTURE.md) describes the system boundaries.

## Stack

| Layer | Choice |
|---|---|
| Frontend | Next.js 16 App Router, React 19, Tailwind v4, TypeScript strict |
| Backend | Python 3.12, FastAPI, SQLAlchemy 2, Pydantic v2 |
| Identity | Keycloak 26.7, OIDC Authorization Code + PKCE, opaque CareFlow sessions |
| Agent layer | agno agents with typed outputs and function-step workflows |
| LLM | OpenAI-compatible API; deterministic fallbacks work without a key |
| Storage | PostgreSQL; uploads on local disk |
| HMS | OpenEMR through the `HMSClient` FHIR/REST boundary |

## Run locally

Prerequisites: Docker, Node 20+, and Python 3.12.

### Ports

| Service | URL | Notes |
|---|---|---|
| Frontend (Next.js) | http://localhost:3000 | what you open in the browser |
| Backend (FastAPI) | http://localhost:8000 | `/docs` for the OpenAPI UI, `/health` for liveness |
| Postgres | localhost:5432 | this project's own `healthcare_agent` database only |
| Keycloak (identity) | http://localhost:8500 | admin console at `/admin/master/console/` |
| OpenEMR (HMS) | http://localhost:8300 (HTTP), https://localhost:8443 (HTTPS) | the hospital system CareFlow talks to |
| OpenEMR's own MariaDB | internal only, not published to the host | OpenEMR's database, separate from Postgres |

### 1. Start the containers

```powershell
docker compose --profile auth up -d db openemr keycloak
```

This also starts `openemr-mariadb` (OpenEMR's own database, a dependency of the `openemr` service).
`infra/keycloak/careflow-realm.json` is imported automatically on Keycloak's first boot — it creates the `careflow`
realm, the `careflow-web` client, and the `patient`/`clinician`/`admin` realm roles, but zero users. Keycloak's own
admin login is `admin` / `KEYCLOAK_ADMIN_PASSWORD`.

Every credential above is a real, non-trivial default (not `postgres`/`admin`/`password`) but is still a **published,
local-dev-only** value — copy [`.env.example`](.env.example) to `.env` in the repo root and change every password in
it before running this anywhere but a laptop. `docker compose` reads `.env` from the working directory automatically.

### 2. OpenEMR one-time setup

On a **fresh** install (first boot of the `openemr` + `openemr-mariadb` volumes), `docker-compose.yml` already
enables the REST/FHIR APIs and the OAuth2 password grant via `OPENEMR_SETTING_*` env vars, and creates the admin
login `admin` / `OPENEMR_ADMIN_PASSWORD` (`OE_USER` / `OE_PASS` in the compose file, default `Careflow@2026` — change
it via **Administration → Users** in the OpenEMR UI, not by editing compose, once the instance already exists). Log
in at http://localhost:8300 to confirm it's up, then register the CareFlow OAuth client from `backend/` (after
creating the venv in step 3 below):

```powershell
python scripts/openemr_register_client.py --base-url http://localhost:8300 --out .env.openemr-client.json
```

This writes the client id/secret to `.env.openemr-client.json` (already gitignored) — copy them into `backend/.env`
as `OPENEMR_CLIENT_ID` / `OPENEMR_CLIENT_SECRET`. Then:

- **Administration → System → API Clients**: find the new *CareFlow* client and click **Enable Client** —
  dynamically registered clients start disabled.
- Set `OPENEMR_USERNAME` / `OPENEMR_PASSWORD` in `backend/.env` to a real OpenEMR user the backend authenticates as
  (the `user/*` scopes need the OAuth2 password grant); the compose demo can reuse `admin` / `Careflow@2026`.

If the APIs were somehow not enabled (e.g. an existing volume from before this compose file), turn them on manually
under **Administration → Config → Connectors**: "OpenEMR Standard FHIR REST API", "OpenEMR Standard REST API", and
"OAuth2 Password Grant".

Adding a capability later means registering a new client (OpenEMR fixes scopes at registration time), not editing
the old one.

### 3. Backend

```powershell
cd backend
python -m venv venv; .\venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(48))"  # set output as AUTH_SESSION_SECRET
# now fill in OPENEMR_CLIENT_ID/SECRET/USERNAME/PASSWORD from step 2 above
python scripts/migrate.py
python scripts/seed.py
uvicorn app.main:app --reload --no-access-log
```

### 4. Frontend

```powershell
cd ../frontend
npm install
copy .env.example .env.local
npm run dev
```

### 5. Create Keycloak users for each role

At http://localhost:8500/admin/master/console/#/careflow/users, create one user per role you want to sign in as
(Users → Create user → Credentials tab → Set password with **Temporary** off → Role mapping tab → assign the
realm role):

- **Patient**: role `patient`. Nothing else needed.
- **Clinician**: role `clinician`, plus two attributes on the Details tab: `clinic_id=qss-demo-clinic` and
  `hms_username=<a real OpenEMR username>` (the `OPENEMR_USERNAME` from step 2, or another OpenEMR user). Sign out
  and back in after setting attributes — Keycloak only puts them in the token at login time.
- **Administrator**: role `admin`. Does not grant clinical case access.

The browser receives an opaque HttpOnly CareFlow session, never an OAuth token, and uses a fixed same-origin Next.js
BFF. FastAPI validates Keycloak tokens server-side and enforces CSRF, role, patient ownership, clinic scope, and
lifecycle gates.

Patients, practitioners, and documents live in OpenEMR. No Keycloak end-user account is committed; Compose bootstrap
credentials are local-only defaults and must be replaced outside the synthetic-data environment.

For a full walkthrough of logging in as each role and testing the intake → triage → review → consultation flow by
hand, see [Manual end-to-end testing](docs/MANUAL_E2E_TESTING.md).

## Surfaces

| Route | Access | Purpose |
|---|---|---|
| `/patient` | authenticated patient | owned visits, identity form, streamed intake, uploads, patient-safe results |
| `/doctor` | authenticated clinician in the active clinic | worklist, review, consultation, summary release |
| `/cases/[id]` | authenticated clinician in the case clinic | full clinical record, audit, agent trace |
| `/admin` | authenticated administrator | clinic configuration without implicit clinical access |

## Guarantees enforced in code

- Only `app/domain/triage_engine.py` sets priority; it is deterministic and every result carries rule evidence.
- Patient case UUIDs are not bearer capabilities; ownership is persisted separately and enforced server-side.
- Clinicians cannot cross clinic boundaries. OpenEMR writes additionally require the password for the Keycloak-mapped
  `hms_username`.
- Consultation and finalization require an approved review; reviewer edits never overwrite patient statements.
- Uploads are stored/displayed only and never enter the triage engine.
- OpenEMR receives an appointment request, never an automatic booking.
- Every state transition writes an application audit event.

## Verification

From `backend`, run `python -m ruff check app tests scripts`, `pytest`, and `alembic check` against PostgreSQL. From
`frontend`, run `npm run lint`, `npx tsc --noEmit`, `npm run build`, and `npm run test:e2e` with the local database and
Keycloak profile running. CI repeats these checks and performs Python/npm advisory and secret scans.

Authentication and authorization materially reduce the original IDOR risk, but this is not a production or compliance
claim. MFA/passkeys, patient identity proofing and proxies, clinician assignment/handoff/break-glass policy,
encrypted/scanned document storage, hardened infrastructure, tested disaster recovery, and independent security/privacy
review remain required before real patient data.
