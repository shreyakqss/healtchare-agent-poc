# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A local, synthetic-data POC for an AI-assisted patient care workflow: intake → patient profile → AI pre-screening → department/doctor recommendation → clinician review → consultation notes → final visit summary.

`PROJECT_FOUNDATION.md` is the authoritative spec (vision, scope, phased plan). `healthcare-agentic-poc-plan.md` is the earlier, narrower triage-focused plan — still accurate on data models and API shape. Phase 1 (a working end-to-end demo) is implemented; Phase 2 is agent/prompt refinement, Phase 3 platform extension.

## Commands

Backend — **run from `backend/`**, imports are top-level absolute (`from config import settings`):

```powershell
.\.venv\Scripts\Activate.ps1         # venv lives at backend\.venv (Python 3.14)
python scripts/seed.py --reset       # create tables + seed rules and 5 synthetic cases
pytest tests/                        # triage engine, hospital config, voice audio + speech segmentation, patient agent
uvicorn main:app --reload            # http://localhost:8000, docs at /docs
```

Voice intake is optional and installed second: `pip install "fastrtc[stt,tts]==0.0.34"`. It is **not installed** in the current venv — the core requirements were installed without it, so `/voice/status` reports unavailable, the portal hides voice mode, and text intake is untouched. The models download on first use, so warm one before a demo rather than during it.

Frontend (from `frontend/`): `npm run dev` · `npm run build` · `npm run lint`. **Never run `next build` while `next dev` is live on the same `.next`** — Turbopack panics on the HMR state. Stop the dev server first.

Postgres runs on localhost:5432 (`docker compose up -d db` starts a container if you don't have a local instance). The local instance is shared with other POCs on this machine; this project owns the `healthcare_agent` database only.

There is no Alembic — the schema is created from the models, so `seed.py --reset` is how you pick up a model change.

## Non-negotiable constraints

These are enforced in code, not just documented. Don't refactor them away:

- **The rule engine is authoritative.** `services/triage_engine.py` is pure (no LLM, no DB, no I/O) and is the only thing that decides a priority. `agents/urgency_evaluator.py` makes zero LLM calls. Every priority traces to a `TriageRule` row plus an evidence item; a hospital config must always contain a fallback rule with an empty condition or `evaluate()` raises rather than guessing — `hospital_config.validate()` enforces this before any config is written or activated.
- **Human review gates every output.** `POST /cases/{id}/consultation-notes` and `/finalize` return 409 unless a `ClinicalReview` with decision `approve` or `edit` exists. The patient-facing half of that gate is `patient-results.tsx` — see **Frontend**.
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

**Who the patient is is collected in the chat**, not assumed. `name`, `age` and
`gender` are ordinary entries in `required_intake_fields` (asked after the
complaint, because that is what the patient opened the chat to talk about), and
they are three separate fact kinds rather than one `demographic` catch-all — a
patient who gave only their age would otherwise close all three, and the
catch-all was where the model put its inventions. One introduction ("I'm Priya
Nair, 51, female") fills all three at once, which is why they are not merged
into a single question.

The answers are also copied onto `PatientCase.demographics_fixture` by
`symptom_extractor.merge_demographics()`, because the queue and the case header
read demographics and not facts — a row reading "Synthetic patient" for someone
who gave their name three turns ago is the feature looking broken exactly where
it is looked at. **First value stated wins**, so a fixture supplied when the
session opened (the simulator names its patients from the Synthea record) is
never overwritten by a later extraction, and placeholder answers are skipped
because "Declined to answer" is not a name. The fact rows remain the record of
what was said; this is a copy for display.

The extractor's system prompt carries a **worked example** showing one sentence split into reason_for_visit + symptom + duration. Without it llama3.1:8b collapsed all three into a single `reason_for_visit` on every opener tested, so a patient who said "chest pain since this morning" was asked for both again. Prose instructions did not move it; the example did. Keep the example.

**Agents** (`agents/`) are plain async functions taking `(db, ...)` — LangGraph nodes, not classes. Only four touch the LLM: `question_planner`, `symptom_extractor`, `summary_agent`, `task_report_agent`. Each catches `LLMError` and degrades to a documented fallback rather than blocking the workflow, which is also how `seed.py` works with no API key set.

**LLM access** is confined to `services/llm_client.py` — httpx against the **OpenAI** chat-completions API, tenacity retries. No provider SDK is installed or imported anywhere; swapping providers is still a one-file change, and that promise was cashed in when this moved off Ollama. Configured by `LLM_BASE_URL` / `LLM_MODEL` in `backend/.env`; currently `gpt-5.4-nano`.

Two things bite when changing model:

- **Reasoning models reject `temperature`; older chat models reject `reasoning_effort`.** `LLM_SUPPORTS_EFFORT` picks which one is sent, so a family change is a settings change. Getting it wrong is a 400 on every agent call.
- **Strict structured output is fussier than Ollama's grammar was.** `json_schema()` in `schemas/agent_outputs.py` already inlines `$defs` and forces every property into `required` — two of the three conditions strict mode wants. `_strict()` in the client adds `additionalProperties: false` and strips the constraint keywords OpenAI refuses (`minimum`, `maxLength`, `format`, …), which Pydantic emits from ordinary `Field(ge=…)` declarations. If the API still rejects a schema, `chat_json` retries once in plain JSON mode with the schema in the prompt rather than failing the turn.

`health()` retrieves the single configured model rather than listing all of them: the list endpoint read-timed-out on a cold connection and reported a false negative, and asking for `LLM_MODEL` by name also catches a typo in it.

**The model upgrade closed a documented gap.** The extraction table below was measured on local models; on `gpt-5.4-nano` the one-turn introduction "I'm Priya Nair, 51, female. Chest pain since this morning." fills name, age, gender, reason, symptom and duration in a single turn, which is what the worked example in the extractor prompt was fighting for. Keep the example anyway — it costs nothing and the fallback path still matters.

`stream_text()` is the same call with `stream: true`, reading SSE frames (`data: {…}`, terminated by `data: [DONE]`) and yielding `choices[].delta.content`. It is deliberately **not** retried: by the time a stream breaks the patient has read half a sentence, and a silent replay would duplicate it. Only `question_planner` uses it — see below.

**Streaming.** One reply, generated once, delivered two ways. `plan_next_question` takes an `on_token` callback (threaded through `run_config`, beside the DB session, because it is a live callable rather than serialisable state), and `api/intake.py:process_turn` is an async generator emitting `TurnEvent` frames: `token` for the screen, `segment` for speech, `done` for the record. `POST /messages/stream` yields those as SSE (FastAPI 0.141's `EventSourceResponse` — the endpoint is an async generator, not a hand-rolled `StreamingResponse`); `POST /messages` drains the same generator to `done` and returns it. There is no second pipeline and no second LLM call — voice is a consumer of the same frames.

The planner asks for free text rather than constrained JSON. `complete` and `missing_fields` are overwritten by code and `reason` is written locally, which left `question` as the only field the model ever decided — the schema bought nothing and could not be streamed. Code still owns the stopping condition.

Chunks are transport. The **`done` frame is the record**: one `IntakeMessage` per turn holding the whole reply, which is the planner's return value and not necessarily what was streamed — a mid-stream failure falls back to a template, and the client re-renders from `done`, so the half-sentence on screen is replaced rather than left. Per-turn state (the token queue, the speech buffer) is local to one `process_turn` call, which is all "sessions stream independently" needs to mean.

`services/voice.split_for_speech()` cuts the growing reply at sentence, then clause, then a hard character ceiling. It is pure text and loads no model, so intake imports it without dragging in ONNX. A boundary only counts when whitespace follows, so "2.5 days" is not two sentences — hence the `final=True` flush.

**The patient simulator is a patient, not an agent.** It runs synthetic
patients through the whole workflow so the multi-agent system can be watched
handling them independently. **It is backend-only now** — `api/simulation.py`
and `services/patient_agent.py` remain, but the `/simulation` UI was removed
when the frontend was cut down to its user-facing surfaces (see **Frontend**),
so the endpoints have no in-repo caller. Drive them with an HTTP client, or
rebuild a driver against the same public calls the portal makes. Patients are
**Synthea** records (`services/synthea.py`): a real CSV export dropped in
`backend/data/synthea/csv/` wins, otherwise the bundled `data/patients.yaml`,
whose comments map each block to the export column it mirrors. Only what a
patient could actually say is read — demographics, active conditions, active
medications, allergies and the reason for the latest encounter.

`services/patient_agent.py` splits the two halves: **the record decides what is
true** (`answers_for()` derives one sentence per intake field, so the patient
cannot report a drug Synthea never gave them), **the model decides how it is
said**. The LLM is handed exactly one fact and told to state it; a reply that
drops the fact is discarded for the derived sentence, because a small model
answers "do you take any medication?" with a fluent, useless "Yes." and the
field then never fills. `source: "script"` on the reply says that happened, and
the simulation shows it.

The driver was **entirely a client** of the ordinary API (it lived at
`frontend/src/lib/simulation.ts`, now deleted): start session, consent, turns,
prescreen, review, notes, finalise are the calls the portal and dashboard
already make, and `POST /simulation/patients/{id}/reply` is the only
simulation-specific endpoint there is. That is what makes it re-creatable
anywhere. `api/simulation.py` imports no agent, no graph and no workflow,
exactly like `api/voice.py`. A simulated case is an ordinary case: it appears
in the dashboard, and `demographics.simulated` is a UI label no backend code
branches on — the dashboard still renders it as a `sim` tag when present.

Two defects the first end-to-end run found, both pre-existing and both fixed:
intake's placeholder answers (`NOT_CAPTURED` and friends) were reaching the
allergy/medication conflict check, where the same sentinel in both rows matched
*itself* and escalated the case to high — `urgency_evaluator.clinical_entries()`
now drops them before the engine sees them, and the rows still stand in the
record. And the extractor's prompt had a worked example for facts but none for
allergies or medications, so a stated medicine produced no row at all; there is
now a second example, per this file's own lesson that prose does not move it.

**Extraction quality is bounded by the configured model**, and it is the
extractor that feels it first. Measured on the same prompts, back when this ran
on local Ollama models — kept because it is the clearest statement of what
degrades, and of what to re-test after any model change:

| The patient said | `gpt-5.4-nano` (current) | `llama3.1:8b` | `gemma3:1b` |
|---|---|---|---|
| "I'm allergic to Penicillin V." | allergy | allergy | **medication** |
| "I take Amlodipine 5 MG Oral Tablet." | medication | medication | nothing, plus an invented hypertension history |
| "I'm male." | gender | gender | **name** |
| "I'm Priya Nair, 51, female." | name + age + gender | name + age + gender | name only |

Nothing here is guessed around: a field the extractor could not read closes as
`NOT_CAPTURED` and the clinician is pointed at the transcript, which is the
documented behaviour. The `sim_meera` fixture exists to demonstrate the
allergy/medication conflict escalation, and it needs a model that can tell an
allergy from a medication — which is the row above that used to fail.

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

**The frontend ships only what an actual user touches.** One surface per role,
plus one for setup:

| Route | Who it is for |
|---|---|
| `/` | the patient — chat, their records, their results |
| `/doctor` | one doctor — their own worklist and the consultation |
| `/dashboard` | clinic staff — queue, patients, doctors, clinic-wide data |
| `/cases/[id]` | anyone who needs one case in full, agent trace included |
| `/hospital` | an administrator — departments, doctors, triage rules |

`/hospital` is deliberately **not** in the main tabs: it is setup, not shift
work, so it sits as a quiet "Configuration" link in the header (`AdminLink` in
`nav-links.tsx`). The main tabs are patient, doctor and staff.

**The patient surface has no start step.** `patient-portal.tsx` is a shell with
a sidebar over three views — `patient-chat.tsx`, `patient-records.tsx`,
`patient-results.tsx`. The patient lands in a live chat with the assistant
already speaking; `ensureSession()` opens the `IntakeSession` and posts consent
on their *first message or upload*, so nothing is created for someone who only
looked at the page. The consent notice above the composer is what they act on.
That is a deliberate trade of a click-through gate for a direct screen — if a
deployment needs affirmative consent, `ensureSession` is the one place to put
it back. **The chat is never unmounted**; switching tabs hides it with a class,
because unmounting would discard the transcript, the in-flight stream and the
session id.

**`patient-results.tsx` is the review gate made visible**, and it is the one
file where "what may a patient see" is decided. It reads summary fields *by
name*, never by iteration, so a new backend key cannot leak into it: the
pre-screening summary never appears (it is written before any clinician has
read the case), the triage priority never appears in any form (a patient
reading "HIGH" hears a clinical verdict nobody gave them), department and
doctor appear only once `review.decision` is `approve`/`edit`, and
`draft_care_task` is skipped because it carries the priority. Keep that shape.

**There is no patient account.** The backend has no patient table and
`GET /cases` returns the whole clinic, so "my visits" cannot be asked of the
server. `lib/patient-history.ts` remembers case ids in `localStorage` and the
portal loads each with `getCase`; the UI says so rather than pretending
otherwise. Replacing it means a patient id on `PatientCase` plus
`GET /patients/{id}/cases`, after which every caller in that module becomes an
API call and the screens above it do not change. The staff Patients view groups
by `demographics.name` for the same reason, and deliberately does *not* merge
unnamed patients into one row.

**The doctor surface is the clinical loop in the order the backend enforces**:
review → record the consultation → release. `/doctor` has no auth — picking a
name from the roster is the whole of it, and every action is audited against
that name. Cases are matched to a doctor by `doctor_name`, because that is what
`CaseListItem` carries. A consultation records `consultation_mode`
(`in_person` | `virtual`) and a `prescription` alongside the notes; both are
columns on `ConsultationNote`, deliberately not stuffed into the notes text, so
the patient's copy can render a prescription as a prescription. **Adding them
needs `seed.py --reset`** — there is no Alembic.

The internal-facing `/ops` (AI Operations Center) and `/simulation` surfaces
were **removed** — they were built to watch the system work, not to use it.
Recover them from git history if you need them again; don't add a third tab
back into the patient/staff nav. `lib/agents.ts` was trimmed to what the case
detail still needs (`buildPipeline`, `timeline`), and the cross-case rollups
those two surfaces owned — `aggregate`, `streamMetrics`, `voiceMetrics`,
`currentStep`, `mean` — went with them; the audit rows they read are all still
written, so they are re-derivable.

Three things this Next version does differently from most training data:

- `params` is a **Promise** — `const { id } = await params`, typed as `PageProps<'/cases/[id]'>`. Those route types are generated by `next build`/`next dev`, so `tsc --noEmit` fails on a brand-new route until you've run one.
- The React Compiler lint rule `react-hooks/set-state-in-effect` **fails the build** on fetch-on-mount. Pages fetch initial data server-side and pass it into a client component as `initial*` props; client components refetch only in event handlers. Don't reintroduce `useEffect(() => { void load() }, [])`.
- `react-hooks/purity` **fails the build** on `Date.now()` during render — including in a server component. Read the clock in a `useState(() => Date.now())` initialiser or an event handler, and put `suppressHydrationWarning` on anything rendering a locale-formatted timestamp.

**Design system.** Semantic tokens live in `@theme` in `globals.css` (`ink`/`surface`/`raised`/`line`, `text`/`dim`/`faint`, `accent`/`on-accent`/`info`, `high`/`med`/`low`) and every primitive — `Panel`, `Metric`, `Tag`, `Donut`, `BarList`, `Spark`, `Button`, the icon set — is in `lib/ui.tsx`, unmarked so it renders in both server and client trees. There is no chart or icon dependency; `package.json` is still just Next, React and Tailwind. Tailwind only emits classes it can see as **literal strings**, so never interpolate a colour into a class name.

**Theming.** A theme is a palette swap and nothing else — light is the `@theme` default and `[data-theme="dark"]` is the single override block, so components never carry two sets of colours. Style against the semantic tokens, never `zinc-*`/`red-*` or a bare `dark:` colour pair. An inline script in the layout resolves `prefers-color-scheme` once and **always stamps `data-theme` on `<html>`** before first paint; that is what lets the CSS have one override block instead of two, and `@custom-variant dark` binds the `dark:` variant to the same attribute so it follows the toggle rather than the OS. `ink` is recessed relative to `surface` in both themes, so an inset block reads as inset either way; type on an accent fill uses `on-accent`, never `ink`.

**Agent trace.** `lib/agents.ts` derives the per-case agent view — pipeline, statuses, timeline — from `AuditEvent` rows plus the artefacts each agent wrote. It is read by the case detail page's agent rail, which is how a clinician sees *why* a priority and department were suggested; that traceability is the product's safety claim, so keep it. There is no telemetry table, so "latency" is usually the real elapsed time between consecutive audit events and is **sub-millisecond on seeded rows**. The planner is the exception — it times its own generation and reports `generation_ms` from `llm.response_streamed`. The extractor still writes no audit row and reports as not recorded rather than being estimated. Don't substitute plausible-looking numbers, and don't surface anything beyond structured inputs, outputs, evidence ids and timings.

`frontend/AGENTS.md` (aliased by `frontend/CLAUDE.md`) is regenerated by `next dev` — commit it with your changes rather than deleting it.

## Gotchas

- `backend/requirements.txt` must stay UTF-8. It was UTF-16 originally and `pip install -r` choked; regenerate with `pip freeze` rather than hand-editing if that recurs.
- `scripts/seed.py` prints ASCII only — the Windows console is cp1252 and mangles anything else.
- CORS in `main.py` is wide open (`allow_origins=["*"]`) — fine for a local demo, not a pattern to copy.
