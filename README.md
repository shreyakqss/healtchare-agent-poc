# CareFlow: AI-assisted patient intake and administrative triage (POC)

A local, synthetic-data proof of concept for a clinic: the intake assistant collects the patient's story once,
approved rules set an **administrative** priority, a care navigator proposes a department/doctor/slot from the
hospital management system, and **nothing reaches the patient before a clinician has reviewed it**.

Workflow and decision support only. It does not diagnose, prescribe, handle emergencies, interpret images, or book
appointments. `healthcare-agentic-poc-plan.md` is the plan this implements; `docs/ARCHITECTURE.md` explains the shape.

## Stack

| Layer | Choice |
|---|---|
| Frontend | Next.js 16 (App Router), React 19, Tailwind v4, one surface per role |
| Backend | Python 3.12, FastAPI, SQLAlchemy 2, Pydantic v2 |
| Agent layer | [agno](https://docs.agno.com) `Agent`s with typed outputs + `Workflow`s of function steps |
| LLM | any OpenAI-compatible model (`gpt-5.4-nano` default); runs on deterministic fallbacks without a key |
| Storage | PostgreSQL; uploads on local disk |
| HMS | in-process mock adapter (FHIR-shaped) behind `HMSClient` |

## Run it

Prerequisites: PostgreSQL, Node 20+, Python 3.12.

```powershell
# 1. database (or use your own Postgres and point DATABASE_URL at it)
docker compose up -d db

# 2. backend
cd backend
python -m venv venv; .\venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env          # set DATABASE_URL and, optionally, OPENAI_API_KEY
python scripts/seed.py --reset  # tables + triage rules + 5 demo cases at different stages
uvicorn app.main:app --reload   # http://localhost:8000/docs

# 3. frontend
cd ../frontend
npm install
npm run dev                     # http://localhost:3000
```

`python scripts/smoke.py` walks one case through the whole API (needs the API running). `pytest` runs unit tests
plus one integration test against the configured database.

## Surfaces

| Route | Who | What |
|---|---|---|
| `/patient` | patient | streamed intake chat, optional HMS record link, documents, results after review |
| `/doctor` | one doctor | worklist → review (approve / edit / reject) → consultation → release summary |
| `/clinic` | clinic desk | queue, patients, doctor load, HMS requests |
| `/cases/[id]` | anyone | full record, audit trail, agent trace |
| `/admin` | administrator | visual builder for departments, doctors, routing keywords, triage rules, intake fields |

## Guarantees enforced in code

- `app/domain/triage_engine.py` is the only thing that sets a priority. Pure, no LLM, every result carries a rule code and evidence.
- `POST /cases/{id}/consultation-notes` and `/finalize` return **409** until a `ClinicalReview` with `approve`/`edit` exists.
- Reviewer edits live in `ClinicalReview.edits`; patient statements (`PatientFact`) are never rewritten; HMS imports are tagged `source=hms`.
- Uploads are stored and displayed only; they never reach the triage engine.
- The HMS adapter only ever receives an appointment *request* (`CareTask.status = draft`).
- Every state change writes an `AuditEvent`; `/cases/{id}/audit` is the timeline the UI renders.

Synthetic fixtures only. No real PHI.