# Architecture

## Backend (`backend/app`)

```
app/
  main.py              create_app(): CORS, response hardening, /health, /ready, router mount
  core/                settings (pydantic-settings), logging (PHI redaction), domain errors -> HTTP
  security/            OIDC verification, opaque sessions, CSRF, role/clinic/case authorization
  db/                  Base (uuid id + created_at), engine/session, db_session() unit of work
  models/              SQLAlchemy tables (identity/session/ownership, intake, case, clinical, audit)
  schemas/             request / response contracts (the frontend mirrors responses.py by hand)
  domain/              PURE rules, no DB / LLM / I/O:
                         triage_engine (the only thing that sets a priority), routing, intake_fields,
                         lifecycle (status graph), demographics (age from birth date)
  services/            orchestration with a DB session:
                         intake_service      session, consent, identity form, streamed clinical turn loop
                         attachment_service  upload (store + advisory kind check + HMS forward), skip
                         review_service      clinician review -> APPROVED / REJECTED
                         consultation_service consultation notes + the finalisation gate
                         clinician_identity  per-action HMS login check -> 401
                         case_repo           read helpers + the intake completeness gate
                         workflow_jobs       leased PostgreSQL queue, retries, recovery worker
                         workflow_operations checkpointed external-operation ledger
                         auth_maintenance    bounded session/rate-limit cleanup
                         pagination          stable cursor encoding and validation
                         hospital_config     YAML per clinic, active pointer, validation
                         triage_rules        YAML rules -> triage_rules table
                         attachments         file storage + text extraction
                         audit, lifecycle    the only writers of AuditEvent / session.status
                         hms/                what CareFlow sends the HMS and how it degrades:
                           clinic (the facility = the clinic's identity), documents (push with
                           one retry), audit_forward (mirror audit notes), intake_sync
                           (approved-intake payload), roster (live doctors over YAML)
  agents/              agno Agents - one typed async function each, no persistence:
                         fact_extractor, question_planner (streams), discrepancy_checker,
                         summary_writer, visit_reporter
  workflows/           prescreen/finalize steps invoked by durable workflow jobs
  integrations/hms/    HMSClient protocol + get_hms() factory (use_hms() is the test seam)
                         openemr/        the only implementation: auth (OAuth2 + OIDC), scopes,
                                         fhir (pure mapping), rest (standard API - clinical writes),
                                         client (HMSClient)
  api/v1/              thin routers per resource + serializers (ORM -> response models)
data/
  hospitals/*.yaml     one clinic per file; file stem = hospital id; active.txt names the live one
```

There is no fixture data anywhere and no stand-in hospital system. Patients, practitioners, documents and
the clinic's own identity all live in OpenEMR; `data/hospitals/*.yaml` holds clinic *policy* only
(departments and the specialty codes that map practitioners into them, routing keywords, appointment types,
triage rules, required intake fields). The integration tests talk to the real OpenEMR from `backend/.env`
and skip - never silently pass - when it is unreachable (`tests/conftest.py`).

### Layering rule

`api -> services -> domain`, `services -> agents`, `workflows -> services / agents / domain`.
`domain` imports nothing from the app. `agents` never import models or sessions. Routers hold no business
logic: every gate, side effect and audit write lives in a service. `integrations` are reached only through
`get_hms()` and the `HMSClient` protocol; `services/hms/` is the application-side policy on top of it.

### The case lifecycle

`CREATED -> INGESTING -> ANALYZING -> NEEDS_REVIEW -> APPROVED -> COMPLETED` (+ `REJECTED`, `FAILED`).
`domain/lifecycle.py` is the guard; `services/lifecycle.transition()` is the only writer and audits every change.

### Where the LLM is - and is not

| Step | Decides | LLM? |
|---|---|---|
| Fact extraction | what the patient stated -> typed facts | yes (fallback: raw text kept as a fact) |
| Question planning | wording of the next question | yes (fallback: template). *Which* field and *when to stop* is code |
| Discrepancy check | patient statement vs document / HMS record (clinician-facing flags) | yes (fallback: no flags) |
| Urgency evaluation | priority, rule codes, evidence, warnings | **never** |
| Care navigation | department / doctor / appointment type / HMS slot | **never** (keyword map + rule hint + live roster) |
| Briefing / visit summary | prose over recorded facts | yes (fallback: plain listing) |
| Review | approve / edit / reject | human |
| Care task | draft appointment request to the HMS | **never** |

Every agent raises `AgentUnavailable`; callers degrade to the documented fallback and record which path ran
(`generated_by`, `planner`, `extraction.mode` in the audit payloads) so the UI can say "AI draft" vs "plain listing".

### Clinician identity

Keycloak authenticates the clinician and supplies `clinician`, `clinic_id`, and `hms_username` claims. FastAPI first
requires the clinician role and the case's clinic, then binds review/note/finalize payloads to that `hms_username`.
The clinician enters only that OpenEMR account's password for these step-up HMS writes;
`services/clinician_identity.verify_clinician()` verifies it and records the returned Practitioner identity. The UI no
longer lets a user impersonate another roster entry.

### Authentication and authorization

`careflow-web` uses OIDC Authorization Code + PKCE. FastAPI owns the code exchange and stores encrypted access,
refresh, and ID tokens in `auth_sessions`; the browser receives only a random HttpOnly `careflow_session` plus a
double-submit CSRF cookie. Next.js exposes fixed login/callback/logout handlers and a fixed `/api/careflow/*` BFF, so
tokens and backend addresses never enter client JavaScript. Sessions are absolute-lifetime bounded, refresh tokens are
rotated under a row lock, logout revokes the local row, and bearer clients still use strict RS256/JWKS verification.

`ApplicationUser` is keyed by immutable `(issuer, subject)`. `CaseOwner` binds each patient-created case to an
application user. Patient endpoints require that row and return a patient-specific projection. Clinician reads require
`clinician` plus a `clinic_id` equal to the case/active clinic. Admin endpoints require `admin`; that role alone cannot
read clinical cases. Assignment, handoff, coverage, proxies, and break-glass remain explicit domain-policy gaps.

### Intake

Two steps. An authenticated patient creates an owned case. The identity form (name, date of birth, gender, contact,
address) is submitted once and creates the patient in the HMS (`register_patient`), so the case is HMS-linked from that
point. Existing-record search/link is intentionally unavailable until patient identity-proofing, record matching, proxy,
and recovery policy exists. Clinical fields are then asked one at a time.

A required field is open until a row satisfies it. A denial writes no fact, so each assistant question stores
`asks_field` and the next turn closes it with one of three sentinels (`None reported by patient`,
`Declined to answer`, `Answered - see the intake transcript`). Intake never asks the same field twice and always
closes with a spoken message. `MAX_ASSISTANT_QUESTIONS` is a backstop, not the normal exit.

Once `case_repo.ready_for_prescreen()` holds, CareFlow atomically enqueues a durable pre-screen job: every required
field must be present and every required attachment kind uploaded or explicitly skipped. Leases recover abandoned jobs;
completed steps are checkpointed so a retry resumes instead of replaying local work.

### Streaming

`POST /intake-sessions/{id}/messages/stream` is SSE: `token` frames while the planner writes, one `done` frame with
the canonical turn (what is stored), or a final `error` frame. `POST .../messages` drains the same generator.

### The HMS boundary

`HMSClient` is the whole contract (`integrations/hms/base.py`). CareFlow reads patients, practitioners, encounters,
conditions, allergies, medications, and documents from OpenEMR. It writes patient registrations, approved clinical
content, documents, and appointment requests; CareFlow-local workflow state, audit events, consent, rules, and agent
traces do not cross that boundary. Appointment requests are always `proposed`/`requested`, never booked; only
clinician-approved content is pushed, and every push is checkpointed and audited. OpenEMR does not accept an
idempotency key, so an ambiguous remote success still requires reconciliation before this can be exactly-once.

## Frontend (`frontend/src`)

```
app/                 routes only (server components fetch, pass initial* props)
app/api/auth/        login, callback and logout BFF handlers
app/api/careflow/    fixed-path authenticated backend proxy for browser requests and SSE
components/ui/       primitives (button, card, badge, form, data, dialog, feedback, tabs, icons)
components/layout/   AppShell (sidebar + top bar), PageHeader, ThemeToggle
features/<area>/     intake, doctor, case, admin - screen logic, split into small files
lib/api/             browser/server clients, SSE reader, typed resource modules, response types
lib/auth.ts          server-only current-user and role gates
lib/                 constants (labels), utils (formatting), fixed backend proxy helpers
```

Design tokens live in `app/globals.css` (`@theme`, light default, `[data-theme="dark"]` override). Components use
semantic tokens only. `features/intake/patient-results.tsx` consumes the backend's patient-safe DTO; the browser never
receives triage priority, evidence, clinician notes, audit, or task internals. Patient visits come from server-enforced
ownership, never local storage. `features/doctor/credential-fields.tsx` is the step-up block for gated HMS actions.

## Extending

- **Another HMS**: implement `HMSClient` under `integrations/hms/<vendor>/`, add it to `get_hms()`, switch
  `HMS_PROVIDER`. Nothing above the protocol changes.
- **Another LLM provider**: `app/agents/llm.py::build_model()`.
- **A new agent**: add `app/agents/<name>.py` (typed output, `AgentUnavailable`), call it from a workflow step.
- **A new gated action**: authenticate, enforce role/resource scope, bind the HMS username where needed, then call a service.
- **A new clinic**: drop a YAML in `data/hospitals/` or use `/admin`.
- **Schema change**: edit the model, generate and review an Alembic revision, then verify upgrade and downgrade with `tests/test_migrations.py`. Deploy with `python scripts/migrate.py`.

## HIPAA technical safeguards

This POC is meant to run against a test OpenEMR holding no real patient records, but a few technical
safeguards are in place as a baseline: production logs are structured, carry a generated request ID and route template,
and scrub phone-number- and MRN-shaped tokens before emission; Uvicorn access logs are disabled so callback query
parameters and resource IDs are not copied into logs; HMS failures are logged by exception *type* only; and an unfinished intake session
(`CREATED`/`INGESTING`) older than `SESSION_TIMEOUT_MINUTES` is rejected on next access. What is deliberately
*not* addressed here: the Postgres data volume and `UPLOAD_DIR` (uploaded documents) are stored as plaintext on
local disk - a production deployment must run these on an encrypted volume or a managed database with
encryption-at-rest. OAuth tokens are encrypted in PostgreSQL and represented in the browser only by a random HttpOnly
session cookie. Versioned key rotation, lazy re-encryption, revocation, and bounded cleanup are implemented; key custody
still belongs in a managed secret platform. This POC serves plain HTTP
locally; production must use TLS, `AUTH_COOKIE_SECURE=True`, exact HTTPS origins, MFA/passkeys for staff/admin, and an
independent privacy/security assessment.
