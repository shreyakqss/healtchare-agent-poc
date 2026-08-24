# Architecture

## Backend (`backend/app`)

```
app/
  main.py              create_app(): CORS, error handlers, /health, router mount
  core/                settings (pydantic-settings), logging, domain errors → HTTP
  db/                  Base (uuid id + created_at), engine/session, db_session() unit of work
  models/              SQLAlchemy tables (intake, case, facts, triage, clinical, care_task, audit)
  schemas/             request / response contracts (the frontend mirrors responses.py by hand)
  domain/              PURE rules: triage_engine, routing, intake_fields, lifecycle  (no DB, no LLM)
  services/            orchestration with a DB session: intake_service, case_repo, hospital_config,
                       triage_rules (YAML → table sync), attachments, audit, lifecycle
  agents/              agno Agents — one typed async function each, no persistence:
                       fact_extractor, question_planner (streams), summary_writer, visit_reporter
  workflows/           agno Workflows of async function Steps: prescreen, finalize
  integrations/hms/    HMSClient protocol + MockHMS (patients, practitioners, slots, requests)
  api/v1/              routers per resource + serializers (ORM → response models)
data/
  hospitals/*.yaml     one clinic per file; file stem = hospital id; active.txt names the live one
  hms/patients.yaml    synthetic HMS registry
  seed/cases.yaml      demo cases, each pushed to a chosen stage through the real workflows
```

### Layering rule

`api → services → domain`, `services → agents`, `workflows → services/agents/domain`.
`domain` imports nothing from the app. `agents` never import models or sessions.
`integrations` are reached only through their protocol (`get_hms()`).

### The case lifecycle

`CREATED → INGESTING → ANALYZING → NEEDS_REVIEW → APPROVED → COMPLETED` (+ `REJECTED`, `FAILED`).
`domain/lifecycle.py` is the guard; `services/lifecycle.transition()` is the only writer and audits every change.

### Where the LLM is — and is not

| Step | Decides | LLM? |
|---|---|---|
| Fact extraction | what the patient stated → typed facts | yes (fallback: raw text kept as a fact) |
| Question planning | wording of the next question | yes (fallback: template). *Which* field and *when to stop* is code |
| Urgency evaluation | priority, rule codes, evidence, warnings | **never** |
| Care navigation | department / doctor / appointment type / HMS slot | **never** (keyword map + rule hint) |
| Briefing / visit summary | prose over recorded facts | yes (fallback: plain listing) |
| Review | approve / edit / reject | human |
| Care task | draft appointment request to the HMS | **never** |

Every agent raises `AgentUnavailable`; callers degrade to the documented fallback and record which path ran
(`generated_by`, `planner`, `extraction.mode` in the audit payloads) so the UI can say "AI draft" vs "plain listing".

### Intake loop

A required field is open until a row satisfies it. A denial writes no fact, so each assistant question stores
`asks_field` and the next turn closes it with one of three sentinels (`None reported by patient`,
`Declined to answer`, `Answered - see the intake transcript`). Intake never asks the same field twice and always
closes with a spoken message. `MAX_ASSISTANT_QUESTIONS` is a backstop, not the normal exit.

When an intake is started with an HMS `mrn`, the record's demographics, conditions, medications and allergies are
imported as `source=hms` rows: they satisfy the corresponding required fields (less re-asking) and stay
distinguishable from patient statements everywhere they are shown.

### Streaming

`POST /intake-sessions/{id}/messages/stream` is SSE: `token` frames while the planner writes, one `done` frame with
the canonical turn (what is stored), or a final `error` frame. `POST …/messages` drains the same generator.

## Frontend (`frontend/src`)

```
app/                 routes only (server components fetch, pass initial* props)
components/ui/       primitives (button, card, badge, form, data, dialog, feedback, tabs, icons)
components/layout/   AppShell (sidebar + top bar), PageHeader, ThemeToggle
features/<area>/     intake, doctor, clinic, case, admin — screen logic, split into small files
lib/api/             fetch client, SSE reader, typed resource modules, response types
lib/                 constants (labels), utils (formatting)
```

Design tokens live in `app/globals.css` (`@theme`, light default, `[data-theme="dark"]` override). Components use
semantic tokens only. `features/intake/patient-results.tsx` is the patient-facing review gate: it reads fields by
name and never shows a priority or the pre-screening briefing.

## Extending

- **Real HMS / FHIR**: implement `HMSClient` (e.g. `FhirHMS`) and switch `HMS_PROVIDER`. Nothing else changes.
- **Another LLM provider**: `app/agents/llm.py::build_model()`.
- **A new agent**: add `app/agents/<name>.py` (typed output, `AgentUnavailable`), call it from a workflow step.
- **A new clinic**: drop a YAML in `data/hospitals/` or use `/admin`.
- **Schema change**: edit the model, `python scripts/seed.py --reset` (no Alembic in the POC).