# Healthcare Agentic POC

A local, synthetic-data proof of concept for an AI-assisted patient care workflow — from patient intake through clinician preparation and post-consultation documentation.

This is workflow and decision support only. It does not diagnose, prescribe, handle emergencies, interpret medical images, or release anything to a patient without authorized human review.

See `PROJECT_FOUNDATION.md` for the full vision and phased plan.

## What It Demonstrates

- Guided patient intake with adaptive follow-up questions
- Structured symptom, history, allergy and medication capture
- Upload of medical records — lab reports, radiology and pathology images, prescriptions
- Rule-based administrative triage with rule IDs and evidence
- Department and doctor recommendation from a configurable hospital
- Clinician-facing pre-screening summary
- Clinician review: approve, edit, or reject
- Consultation notes and an AI-generated final visit summary
- Consent and audit timeline for the whole case
- A staff dashboard of incoming patients and case progress

## Technical Stack

- **Frontend:** Next.js 16 / React 19 / Tailwind v4
- **Backend:** Python 3.12 / FastAPI / SQLAlchemy 2
- **Orchestration:** LangGraph `StateGraph` — three graphs split at the human-review boundaries
- **Storage:** PostgreSQL; uploaded files on the local filesystem
- **LLM:** local Ollama behind an `LLMClient` interface (one file to swap providers)

## Running It

Prerequisites: PostgreSQL on `localhost:5432`, [Ollama](https://ollama.com), Node 20+, Python 3.12.

```powershell
# 1. Database — use your own Postgres, or start one:
docker compose up -d db

# 2. Local model
ollama serve
ollama pull llama3.1:8b

# 3. Backend
cd backend
copy .env.example .env          # then set DATABASE_URL if yours differs
pip install -r requirements.txt
python scripts/seed.py --reset  # creates tables, seeds rules + 5 synthetic cases
pytest tests/
uvicorn main:app --reload       # http://localhost:8000/docs

# 4. Frontend
cd ../frontend
npm install
npm run dev                     # http://localhost:3000
```

`seed.py --reset` is repeatable — run it any time to reset the demo.

## Demo Flow

1. **Patient intake** (`/`) — grant consent, answer the assistant's questions, optionally upload a report or image, then submit for review.
2. **Staff dashboard** (`/dashboard`) — see incoming cases with status, priority, department and assigned doctor.
3. **Case view** (`/cases/{id}`) — the clinician sees the patient's facts, the priority with its rule evidence, the routing recommendation, attachments, and the pre-screening summary.
4. **Review** — approve, approve with an edit, or reject. Edits are recorded separately from the patient's original statements.
5. **Consultation** — record notes and follow-up instructions, then finalise.
6. **Final visit summary** — generated from the clinician's notes, with a *draft* scheduling task. Nothing is booked.
7. **Audit timeline** — every consent, status change, and decision on the case.

The seeded cases cover low / medium / high priority, an incomplete intake, and an allergy-medication conflict with attached synthetic reports.

## Configuring the Hospital

`backend/hospital.yaml` defines departments, doctors, appointment types, the specialty keyword map, and the triage rules. Edit it and re-run `python scripts/seed.py --reset` to simulate a different clinic — no agent code changes.

## Scope

Synthetic or de-identified fixtures only, intended for local or QSS-controlled use. Excluded from this POC: autonomous diagnosis, treatment or medication recommendations, emergency-care decisions, medical image interpretation, EMR/FHIR integration, real appointment booking, and production deployment.
