# Healthcare Agentic POC

This is a local, synthetic-data proof of concept for an AI-assisted patient intake and triage workflow. It is designed to support guided intake, structured case capture, routing support, and clinician review for demonstration purposes only.

This project is workflow and decision support only. It does not diagnose, prescribe, handle emergencies, or release clinical recommendations without human review.

## What It Demonstrates

- Guided patient or staff intake
- Structured symptom and history capture
- Administrative triage and routing support
- Clinician-facing summaries with evidence
- Human review, edit, or rejection of recommendations

## Technical Stack

- Frontend: Next.js / React
- Backend: Python / FastAPI
- Orchestration: LangGraph `StateGraph` with human-in-the-loop pauses
- Storage: PostgreSQL plus local filesystem or MinIO for fixtures
- Retrieval: PostgreSQL full-text search and vector search where useful
- LLM access: configurable provider behind an `LLMClient` interface

## Demo Flow

1. Start a synthetic intake session.
2. Collect symptoms, history, allergies, and medications.
3. Ask follow-up questions for missing details.
4. Generate a structured case, routing suggestion, and clinician summary.
5. Review the result before any draft task or report is created.

## Scope

This POC uses synthetic or de-identified fixtures only and is intended for local or QSS-controlled use.
