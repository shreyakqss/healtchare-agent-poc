# CLAUDE.md

Guidance for Claude Code in this repository.

## What this is

CareFlow: a local POC for AI-assisted patient intake → rule-based administrative triage →
department/doctor routing → clinician review → consultation → visit summary + draft care task, running
against a real OpenEMR instance as the hospital system.
`docs/ARCHITECTURE.md` is the map of the code. Read it first.

## Commands

Backend. Run from `backend/` (venv at `backend/venv`, Python 3.12; imports are `app.*`):

```powershell
.\venv\Scripts\Activate.ps1
python scripts/seed.py --reset        # tables + triage-rule sync (the way to pick up a model change)
uvicorn app.main:app --reload         # http://localhost:8000/docs
pytest                                # unit + integration; integration needs DATABASE_URL
python scripts/smoke.py               # end-to-end over HTTP, API + OpenEMR must be running
```

There is no seeded demo data, no synthetic patient registry and no fake hospital system anywhere -
including in the tests. Patients, practitioners, documents and the clinic's own name/address live in
OpenEMR (`docker compose up -d openemr`); `scripts/smoke.py` is how
you get a case end-to-end. The integration tests run against that same OpenEMR, registering real records,
and are skipped with a reason when it is unreachable (`tests/conftest.py`). Only two things are ever
stubbed: the intake LLM agents (quota) and, in a couple of tests, an HMS that deliberately fails so the
degradation paths can be exercised.

Frontend (from `frontend/`): `npm run dev` · `npm run build` · `npm run lint`.
Never run `next build` while `next dev` is live on the same `.next`.

Postgres: `docker compose up -d db` or a local instance; this project owns the `healthcare_agent` database only.
OpenEMR: `docker compose up -d openemr`, then register the OAuth client once
(`python scripts/openemr_register_client.py`). `backend/.env` holds
`DATABASE_URL`, the `OPENEMR_*` settings and optionally `OPENAI_API_KEY`. Without an LLM key every agent
takes its documented fallback, so the whole flow still works, just without generated prose. Without
OpenEMR the API still starts and serves existing cases, but intake cannot register or look up a patient.

Identity: `docker compose --profile auth up -d keycloak`; the realm import is in `infra/keycloak/`.
`AUTH_SESSION_SECRET` is required for browser login. Keycloak owns authentication and coarse roles; FastAPI owns
patient ownership, clinic scope, clinical lifecycle, and action authorization. Next.js is a same-origin BFF and OAuth
tokens must never be exposed to browser code or storage.

## Non-negotiables (enforced in code, keep them that way)

- `app/domain/triage_engine.py` is the only thing that sets a priority. Pure: no LLM, no DB, no I/O. Every
  result carries rule codes + evidence; a hospital config must have a fallback rule (empty condition) or
  `hospital_config.validate()` refuses to write it.
- Human review gates output: `/consultation-notes` and `/finalize` 409 until a `ClinicalReview` with
  `approve`/`edit` exists. `/review`, `/consultation-notes` and `/finalize` all carry the clinician's HMS
  password and the immutable username from the Keycloak `hms_username` claim; mismatches are rejected before
  `clinician_identity.verify_clinician()`. The patient endpoint returns a dedicated safe projection that excludes
  priority, rule evidence, notes, internal summaries, audit, and task internals.
- Every application route is deny-by-default: patient routes require persisted `CaseOwner`, clinician routes require
  the case clinic, and admin alone never grants clinical access. Unsafe cookie-authenticated requests require CSRF.
- Reviewer edits go to `ClinicalReview.edits`; `PatientFact` rows are never rewritten. HMS imports are
  `source=hms`; patient statements are `source=patient`.
- Uploads are stored/displayed only and never reach `triage_engine.evaluate()`.
- The HMS adapter receives appointment *requests* only; `CareTask.status` is always `draft`. Against
OpenEMR that is a chart note for scheduling staff - never a calendar event, which would be a booking.
- OpenEMR is the source of truth for patients, practitioners and documents. Patient self-service record search/linking
  is disabled until identity-proofing and proxy rules exist; the identity form creates the OpenEMR record. Departments, routing keywords
  and triage rules stay clinic policy in `data/hospitals/*.yaml`, and practitioners map to a department by
  NUCC specialty code (`specialty_codes`).
- Test data only - never point `OPENEMR_*` at an instance holding real patient records.

## Architecture in one breath

`api → services → domain`; `services/workflows → agents`; `domain` imports nothing from the app; `agents` (agno)
never touch the DB. Routers are thin: every gate and side effect lives in a service (`attachment_service`,
`review_service`, `consultation_service`, `clinician_identity`, `prescreen_trigger`, `services/hms/*`). Two agno
`Workflow`s (`prescreen`, `finalize`) of async function steps, each step its own `db_session()` unit of work; the
human pause is a workflow boundary, not a checkpoint. Intake turns are a plain async generator in
`services/intake_service.py` because they stream. The HMS is reached only via `get_hms()`; the OpenEMR adapter is
the `integrations/hms/openemr/` package (auth, FHIR mapping, REST mapping, and client orchestration).

Every status write goes through `services/lifecycle.transition()`; every state change writes an `AuditEvent`.

## Things that bite

- Strict structured output: agent output schemas (`app/agents/schemas.py`) must not carry numeric constraints
  (`ge=`, `maxLength`). OpenAI strict mode rejects them.
- Reasoning models reject `temperature`; older chat models reject `reasoning_effort`. `LLM_SUPPORTS_EFFORT`
  picks which one `build_model()` sends.
- The intake loop closes a field the patient denied with a sentinel row (`app/domain/intake_fields.py`). Never
  write `NONE_REPORTED` for an answer that was not a denial.
- `scripts/seed.py` prints ASCII only (Windows console is cp1252).
- Integration tests share `tests/helpers.py` (a valid identity form, fake intake agents, session helpers). They use
  configured synthetic OpenEMR and are skipped when it is unavailable; no production mock provider exists.
- Pre-screening is triggered by `services/prescreen_trigger.fire_if_ready()` from both the closing chat turn and
  the attachment upload/skip endpoints - whichever lands last. It claims the case (`ANALYZING`) synchronously.
- Frontend: `params` is a Promise; no `useEffect` fetch-on-mount (React Compiler lint fails the build). Pages
  fetch server-side and pass `initial*` props; no `Date.now()` in render; Tailwind only sees literal class
  strings, never interpolate a colour. Style with semantic tokens from `globals.css`, never raw palette colours.
- Authenticated server components call FastAPI directly with the opaque session cookie. Client components use only
  `/api/careflow`; never reintroduce `NEXT_PUBLIC_API_URL`, bearer-token storage, arbitrary proxy targets, or localStorage
  case ownership.
- `frontend/AGENTS.md` is regenerated by `next dev`; commit it with your changes.
