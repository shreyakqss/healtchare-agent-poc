# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A local, synthetic-data POC for an AI-assisted patient care workflow: intake → patient profile → AI pre-screening → department/doctor recommendation → clinician review → consultation notes → final visit summary.

`PROJECT_FOUNDATION.md` is the authoritative spec (vision, scope, phased plan). `healthcare-agentic-poc-plan.md` is the earlier, narrower triage-focused plan — still accurate on data models and API shape. Phase 1 (a working end-to-end demo) is implemented; Phase 2 is agent/prompt refinement, Phase 3 platform extension.

## Commands

Backend — **run from `backend/`**, imports are top-level absolute (`from config import settings`):

```powershell
activatevenv AI-POC                  # venv lives at D:\Python\virtual_envs\AI-POC
python scripts/seed.py --reset       # create tables + seed rules and 5 synthetic cases
pytest tests/                        # triage engine test
uvicorn main:app --reload            # http://localhost:8000, docs at /docs
```

Frontend (from `frontend/`): `npm run dev` · `npm run build` · `npm run lint`.

Postgres runs on localhost:5432 (`docker compose up -d db` starts a container if you don't have a local instance). Ollama runs on the host: `ollama serve`, `ollama pull llama3.1:8b`.

There is no Alembic — the schema is created from the models, so `seed.py --reset` is how you pick up a model change.

## Non-negotiable constraints

These are enforced in code, not just documented. Don't refactor them away:

- **The rule engine is authoritative.** `services/triage_engine.py` is pure (no LLM, no DB, no I/O) and is the only thing that decides a priority. `agents/urgency_evaluator.py` makes zero LLM calls. Every priority traces to a `TriageRule` row plus an evidence item; `hospital.yaml` must always contain a fallback rule with an empty condition or `evaluate()` raises rather than guessing.
- **Human review gates every output.** `POST /cases/{id}/consultation-notes` and `/finalize` return 409 unless a `ClinicalReview` with decision `approve` or `edit` exists.
- **Reviewer edits stay separate.** They go to `ClinicalReview.edits`; `PatientFact` rows are never overwritten, so patient statements stay distinguishable from clinician corrections.
- **Uploads are stored and displayed only.** PDFs/text get `extracted_text`; images get `None`. Attachment content is deliberately not passed to `triage_engine.evaluate()` — that's what makes "an attachment can't change a priority" true by construction, not by convention.
- Synthetic fixtures only. No real PHI, no EMR/FHIR integration. Out of scope: diagnosis, treatment or medication recommendations, emergency decisions, image interpretation, real appointment booking.

## Architecture

**Data flow:** one `IntakeSession` → one `PatientCase` → everything else FKs to `patient_cases` with `ondelete="CASCADE"`. `models/database.py` defines a `Base` that gives every table a UUID `id` and a timezone-aware `created_at`, so subclasses declare only their own columns. Import from `models` (not individual modules) so `Base.metadata` is complete.

**Three LangGraph `StateGraph`s** in `workflow/graph.py`, split at the two human boundaries:

| Graph | Trigger | Nodes |
|---|---|---|
| `intake_graph` | one patient message | extract_facts → plan_next_question |
| `prescreen_graph` | `POST /cases/{id}/prescreen` | process_records → evaluate_urgency → navigate_care → summarise → NEEDS_REVIEW |
| `finalize_graph` | `POST /cases/{id}/finalize` | final_summary → COMPLETED |

**No checkpointer.** Durable state is the Postgres tables; the human pause is a graph boundary, not an `interrupt()`. The DB session travels in the run config (`config={"configurable": {"db": db}}`), never in state — it isn't serialisable, and keeping it out means state stays checkpointable if that changes. Adding one needs `langgraph-checkpoint-postgres`, which wants psycopg 3 while this project is on `psycopg2-binary`.

**Status lifecycle** `CREATED → INGESTING → ANALYZING → NEEDS_REVIEW → APPROVED → COMPLETED` (+ `REJECTED`/`FAILED`) is guarded by `workflow/transitions.py`; every status write goes through `apply_transition`, which also audits the change.

**Agents** (`agents/`) are plain async functions taking `(db, ...)` — LangGraph nodes, not classes. Only four touch the LLM: `question_planner`, `symptom_extractor`, `summary_agent`, `task_report_agent`. Each catches `LLMError` and degrades to a documented fallback rather than blocking the workflow, which is also how `seed.py` works with Ollama switched off.

**LLM access** is confined to `services/llm_client.py` (httpx → Ollama `/api/chat`, JSON schema in `format`, tenacity retries). No provider SDK is imported anywhere else — swapping providers is a one-file change. Schemas come from `schemas/agent_outputs.py` via `json_schema()`, which inlines `$defs` because Ollama's grammar compiler handles `$ref` poorly.

**Configurable hospital:** `backend/hospital.yaml` holds departments, doctors, appointment types, the specialty keyword map, and the triage rules. `seed.py` writes the rules into the `TriageRule` table so `rule_ids` reference real rows for the audit trail, while staying editable as text. Read it through `services/hospital_config.py` (cached; call `reload()` after editing).

Note it's a bare file, not a `config/` directory — that name would shadow `config.py` the moment anyone added an `__init__.py`.

## API

Everything mounts under `/api/v1/healthcare` (set once in `main.py`; routers declare only their resource path). FastAPI 0.141 includes routers lazily, so introspecting `app.routes` shows `_IncludedRouter` objects — read `app.openapi()` instead.

Every state-changing endpoint writes an `AuditEvent`; that's what makes `/cases/{id}/audit` a real timeline.

## Frontend

Next.js 16 App Router + React 19 + Tailwind v4 (PostCSS plugin, no `tailwind.config`), TypeScript strict, `@/*` → `./src/*`.

Two things this Next version does differently from most training data:

- `params` is a **Promise** — `const { id } = await params`, typed as `PageProps<'/cases/[id]'>`. Those route types are generated by `next build`/`next dev`, so `tsc --noEmit` fails on a brand-new route until you've run one.
- The React Compiler lint rule `react-hooks/set-state-in-effect` **fails the build** on fetch-on-mount. Pages fetch initial data server-side and pass it into a client component as `initial*` props; client components refetch only in event handlers. Don't reintroduce `useEffect(() => { void load() }, [])`.

`frontend/AGENTS.md` (aliased by `frontend/CLAUDE.md`) is regenerated by `next dev` — commit it with your changes rather than deleting it.

## Gotchas

- `backend/requirements.txt` must stay UTF-8. It was UTF-16 originally and `pip install -r` choked; regenerate with `pip freeze` rather than hand-editing if that recurs.
- `scripts/seed.py` prints ASCII only — the Windows console is cp1252 and mangles anything else.
- CORS in `main.py` is wide open (`allow_origins=["*"]`) — fine for a local demo, not a pattern to copy.
