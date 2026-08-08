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
pytest tests/                        # triage engine, hospital config, voice audio + speech segmentation
uvicorn main:app --reload            # http://localhost:8000, docs at /docs
```

Voice intake is optional and installed second: `pip install -r requirements-voice.txt` (read the file first — it explains the pins fastrtc relaxes). The models download on first use, so warm one before a demo rather than during it.

Frontend (from `frontend/`): `npm run dev` · `npm run build` · `npm run lint`.

Postgres runs on localhost:5432 (`docker compose up -d db` starts a container if you don't have a local instance). Ollama runs on the host: `ollama serve`, `ollama pull llama3.1:8b`.

There is no Alembic — the schema is created from the models, so `seed.py --reset` is how you pick up a model change.

## Non-negotiable constraints

These are enforced in code, not just documented. Don't refactor them away:

- **The rule engine is authoritative.** `services/triage_engine.py` is pure (no LLM, no DB, no I/O) and is the only thing that decides a priority. `agents/urgency_evaluator.py` makes zero LLM calls. Every priority traces to a `TriageRule` row plus an evidence item; a hospital config must always contain a fallback rule with an empty condition or `evaluate()` raises rather than guessing — `hospital_config.validate()` enforces this before any config is written or activated.
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

**Intake never asks the same thing twice.** The rule is `missing_fields()`: a field is outstanding until a row satisfies it. The trap is that a *denial* produces no row — the extractor records only what a patient stated, so "no, I don't have any allergies" writes nothing and the field reads as never asked. That looped: the planner re-asked, the model reworded, and it looked like a fresh question each time until `MAX_ASSISTANT_QUESTIONS` ended the conversation with an empty reply that rendered as nothing at all.

So every assistant question stores the field it was for (`IntakeMessage.asks_field`), and `_settle_last_question` closes it on the next turn by writing a real row. **The value is not one thing** — `NONE_REPORTED` for a denial (`is_denial`), `DECLINED` when the patient asks to move on (`wants_to_move_on`), `NOT_CAPTURED` when they answered and the extractor made nothing of it. Collapsing those was the first attempt and it filed "symptom: None reported" on a chest-pain case; never write a denial the patient did not make. Intake also always closes with a spoken message (`CLOSING`), because returning `question=""` stores no message and reads as a freeze.

The extractor's system prompt carries a **worked example** showing one sentence split into reason_for_visit + symptom + duration. Without it llama3.1:8b collapsed all three into a single `reason_for_visit` on every opener tested, so a patient who said "chest pain since this morning" was asked for both again. Prose instructions did not move it; the example did. Keep the example.

**Agents** (`agents/`) are plain async functions taking `(db, ...)` — LangGraph nodes, not classes. Only four touch the LLM: `question_planner`, `symptom_extractor`, `summary_agent`, `task_report_agent`. Each catches `LLMError` and degrades to a documented fallback rather than blocking the workflow, which is also how `seed.py` works with Ollama switched off.

**LLM access** is confined to `services/llm_client.py` (httpx → Ollama `/api/chat`, JSON schema in `format`, tenacity retries). No provider SDK is imported anywhere else — swapping providers is a one-file change. Schemas come from `schemas/agent_outputs.py` via `json_schema()`, which inlines `$defs` because Ollama's grammar compiler handles `$ref` poorly.

`stream_text()` is the same call with `stream: true`, yielding Ollama's NDJSON chunks. It is deliberately **not** retried: by the time a stream breaks the patient has read half a sentence, and a silent replay would duplicate it. Only `question_planner` uses it — see below.

**Streaming.** One reply, generated once, delivered two ways. `plan_next_question` takes an `on_token` callback (threaded through `run_config`, beside the DB session, because it is a live callable rather than serialisable state), and `api/intake.py:process_turn` is an async generator emitting `TurnEvent` frames: `token` for the screen, `segment` for speech, `done` for the record. `POST /messages/stream` yields those as SSE (FastAPI 0.141's `EventSourceResponse` — the endpoint is an async generator, not a hand-rolled `StreamingResponse`); `POST /messages` drains the same generator to `done` and returns it. There is no second pipeline and no second LLM call — voice is a consumer of the same frames.

The planner asks for free text rather than constrained JSON. `complete` and `missing_fields` are overwritten by code and `reason` is written locally, which left `question` as the only field the model ever decided — the schema bought nothing and could not be streamed. Code still owns the stopping condition.

Chunks are transport. The **`done` frame is the record**: one `IntakeMessage` per turn holding the whole reply, which is the planner's return value and not necessarily what was streamed — a mid-stream failure falls back to a template, and the client re-renders from `done`, so the half-sentence on screen is replaced rather than left. Per-turn state (the token queue, the speech buffer) is local to one `process_turn` call, which is all "sessions stream independently" needs to mean.

`services/voice.split_for_speech()` cuts the growing reply at sentence, then clause, then a hard character ceiling. It is pure text and loads no model, so intake imports it without dragging in ONNX. A boundary only counts when whitespace follows, so "2.5 days" is not two sentences — hence the `final=True` flush.

**Configurable hospital:** `backend/data/hospitals/*.yaml` — one file per clinic, holding departments, doctors, appointment types, the specialty keyword map, and the triage rules. **The file stem is the hospital id**; `hospital.id` inside the YAML is display metadata only. Read it through `services/hospital_config.py` (cached; call `reload()` after editing).

Exactly one clinic is active at a time, named in `data/hospitals/active.txt` (gitignored — local demo state, falling back to `settings.DEFAULT_HOSPITAL_ID`). Every reader in `hospital_config` is parameterless and answers for whichever that is. This is a demo switch, **not concurrent multi-tenancy** — cases carry no hospital id, so a case routed under one clinic can show an unresolved department after a switch.

`services/triage_rules.sync()` reconciles a clinic's YAML rules into the `TriageRule` table so `rule_ids` reference real rows for the audit trail. Both `seed.py` and the `/hospital` API call it. Rows are scoped by `hospital_id` and uniqueness is `(hospital_id, code)` — two clinics numbering a rule `TR-HIGH-001` is expected. Rules dropped from a YAML are marked `retired`, never deleted, so a case triaged before the edit still resolves its rule code; `urgency_evaluator` filters on both columns.

The `/hospital` page (and `api/hospital.py`) is the UI for all of this: view the active clinic, edit it, add one (copied from the active one, so it starts valid), and activate or delete. Saving validates before writing, so an invalid config 422s instead of reaching disk.

It is a **visual builder**, not a YAML editor — departments, doctors, appointment types, routing keywords, triage rules and required intake fields all have real controls, and the org chart is drawn from the document being edited. It reads and writes `/hospital/hospitals/{id}/json`, which is `yaml.safe_load`/`safe_dump` around the same `write_text` validation path; parsing YAML in the browser would have meant a second parser to keep honest. Round-tripping a document **drops the file's comments**, which is why the raw text editor still exists under the Developer section (import/export/copy) and saves through `/yaml` instead. Keep both paths — never make someone learn YAML to add a doctor.

**Voice is an input channel, not an agent.** `services/voice.py` and `api/voice.py` do two things: audio→text (Moonshine) and text→audio (Kokoro), both local ONNX models from `fastrtc` — the components of the reference `local-voice-ai-agent` project. What is deliberately *not* taken from it is its Ollama conversation loop: the healthcare workflow generates every reply. `api/voice.py` imports no agent, no graph, and not even the intake router, so there is no path by which it can triage, route, or answer.

The browser records, downsamples to 16 kHz mono and encodes WAV itself (`lib/audio.ts`), so the backend needs no audio codec beyond the standard library's `wave`. It then calls `/voice/transcribe` and posts the transcript to the ordinary `POST /intake-sessions/{id}/messages/stream` — a spoken turn is not merely treated like a typed turn, it **is** one by the time the workflow sees it. `MessageRequest.channel` records which it was and must never be branched on. Audio is never persisted; the `IntakeMessage` row is the record.

Speech comes off that same stream. `segment` frames are phrases, never tokens, and `lib/audio.ts:speechQueue` synthesises each on arrival while playing them in order — segment n+1 is generated while segment n is heard. `stop()` is the interrupt: it silences playback and drops the queue, touching no conversation state, because the text is already on screen and the turn is already stored. The queue is created per turn, so an interrupt cannot leak into the next one, and text mode creates none at all — a broken TTS model cannot reach typed intake.

Its FastRTC `Stream`/`ReplyOnPause` WebRTC transport was skipped: intake is turn-based and every turn is bound to an `IntakeSession` row, which a peer connection would need a second notion of session state to carry. Revisit only if barge-in latency matters more than keeping one patient API for the UI and the future simulator.

Install is optional and second — see `requirements-voice.txt`, which also explains the two pins fastrtc relaxes. Without it `/voice/status` reports unavailable, the portal hides voice mode, and text intake is untouched.

Every stage writes an `AuditEvent` (`voice.input_received`, `voice.transcribed`, `voice.synthesised` — one per segment, carrying its index — and the `*_failed` pairs), and `process_turn` writes `intake.turn_processed` for **both** channels with the intake graph's real duration. That timing covers extraction *and* planning together, so it is reported as the workflow's time in the trace and in `voiceMetrics`. `lib/agents.ts:voiceMetrics` rolls the voice stages up for the operations centre.

`process_turn` also writes `llm.response_streamed` per reply: `ttft_ms`, `generation_ms`, `chunks`, `characters`, `speech_segments`. This is the one place a real per-agent duration exists — `generation_ms` is the planner's own time, so the planner row reports it instead of "not recorded". `ttft_ms` runs from the *start of the turn* and therefore includes extraction: that is the wait the patient actually sits through, and the extractor's share of it is still not measured, so it is still not guessed at. `lib/agents.ts:streamMetrics` rolls this up into the operations centre's Streaming panel.

## API

Everything mounts under `/api/v1/healthcare` (set once in `main.py`; routers declare only their resource path). FastAPI 0.141 includes routers lazily, so introspecting `app.routes` shows `_IncludedRouter` objects — read `app.openapi()` instead.

Every state-changing endpoint writes an `AuditEvent`; that's what makes `/cases/{id}/audit` a real timeline.

`POST /intake-sessions/{id}/messages` and `.../messages/stream` are the same turn — see **Streaming** above. The UI only uses the streaming one; the plain one exists for callers that have no use for a stream (the tests, the future simulator). A failure mid-stream arrives as a final `error` frame, not a status code: the 200 was committed before the first token existed.

## Frontend

Next.js 16 App Router + React 19 + Tailwind v4 (PostCSS plugin, no `tailwind.config`), TypeScript strict, `@/*` → `./src/*`.

Four surfaces: `/` patient portal, `/dashboard` staff queue, `/cases/[id]` case detail, `/ops` AI Operations Center, plus `/hospital` (the builder).

Three things this Next version does differently from most training data:

- `params` is a **Promise** — `const { id } = await params`, typed as `PageProps<'/cases/[id]'>`. Those route types are generated by `next build`/`next dev`, so `tsc --noEmit` fails on a brand-new route until you've run one.
- The React Compiler lint rule `react-hooks/set-state-in-effect` **fails the build** on fetch-on-mount. Pages fetch initial data server-side and pass it into a client component as `initial*` props; client components refetch only in event handlers. Don't reintroduce `useEffect(() => { void load() }, [])`.
- `react-hooks/purity` **fails the build** on `Date.now()` during render — including in a server component. Read the clock in a `useState(() => Date.now())` initialiser or an event handler, and put `suppressHydrationWarning` on anything rendering a locale-formatted timestamp.

**Design system.** Semantic tokens live in `@theme` in `globals.css` (`ink`/`surface`/`raised`/`line`, `text`/`dim`/`faint`, `accent`/`on-accent`/`info`, `high`/`med`/`low`) and every primitive — `Panel`, `Metric`, `Tag`, `Donut`, `BarList`, `Spark`, `Button`, the icon set — is in `lib/ui.tsx`, unmarked so it renders in both server and client trees. There is no chart or icon dependency; `package.json` is still just Next, React and Tailwind. Tailwind only emits classes it can see as **literal strings**, so never interpolate a colour into a class name.

**Theming.** A theme is a palette swap and nothing else — light is the `@theme` default and `[data-theme="dark"]` is the single override block, so components never carry two sets of colours. Style against the semantic tokens, never `zinc-*`/`red-*` or a bare `dark:` colour pair. An inline script in the layout resolves `prefers-color-scheme` once and **always stamps `data-theme` on `<html>`** before first paint; that is what lets the CSS have one override block instead of two, and `@custom-variant dark` binds the `dark:` variant to the same attribute so it follows the toggle rather than the OS. `ink` is recessed relative to `surface` in both themes, so an inset block reads as inset either way; type on an accent fill uses `on-accent`, never `ink`.

**Agent trace.** `lib/agents.ts` derives the whole agent view — per-case pipeline, statuses, timeline, aggregate performance — from `AuditEvent` rows plus the artefacts each agent wrote. There is no telemetry table, so "latency" is usually the real elapsed time between consecutive audit events and is **sub-millisecond on seeded rows**. The planner is the exception — it times its own generation and reports `generation_ms` from `llm.response_streamed`. The extractor still writes no audit row and reports as not recorded rather than being estimated. Don't substitute plausible-looking numbers, and don't surface anything beyond structured inputs, outputs, evidence ids and timings.

`/ops` fans out one `getCase` + `audit` per case server-side. Fine at POC scale; batch it before it ever serves a real queue.

`frontend/AGENTS.md` (aliased by `frontend/CLAUDE.md`) is regenerated by `next dev` — commit it with your changes rather than deleting it.

## Gotchas

- `backend/requirements.txt` must stay UTF-8. It was UTF-16 originally and `pip install -r` choked; regenerate with `pip freeze` rather than hand-editing if that recurs.
- `scripts/seed.py` prints ASCII only — the Windows console is cp1252 and mangles anything else.
- CORS in `main.py` is wide open (`allow_origins=["*"]`) — fine for a local demo, not a pattern to copy.
