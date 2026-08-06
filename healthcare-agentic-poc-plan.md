# Healthcare Agentic POC Plan

## AI Patient Intake and Triage Assistant

### Goal

Build a QSS/local, customer-facing demonstration for a clinic or care-navigation team. A patient or staff member completes a guided intake; the system structures the information, applies approved administrative triage rules, recommends a care pathway, and generates a clinician-ready summary for human review.

This is workflow and decision support. It must not diagnose, prescribe, make emergency decisions, or release clinical recommendations without authorized human review.

### Delivery Constraints

- Build in parallel with the fintech POC; target completion is approximately three weeks.
- Run only in a QSS-controlled or local environment.
- Use synthetic or de-identified fixtures only: no real PHI, client data, or live EMR/HIS/FHIR integrations.
- No formal QA phase; perform developer-led smoke, happy-path, exception-path, and demo-repeatability checks.
- Use Docker Compose or local services with a seeded database and documented startup command.
- No patient-impacting output is released before authorized human review.

### Shared Technical Baseline

- **Frontend:** React/Next.js with patient-intake and clinician-review views.
- **Backend:** Python/FastAPI, Pydantic contracts, SQLAlchemy, asynchronous runs.
- **Orchestration:** LangGraph `StateGraph` with explicit states and human-in-the-loop pauses.
- **Storage:** PostgreSQL for cases, runs, reviews, and audit events; local filesystem or MinIO for fixtures.
- **Retrieval:** PostgreSQL full-text search plus vector search where useful; every result carries a source ID.
- **LLM:** configurable provider behind an `LLMClient` interface, with a local/QSS default.
- **Observability:** structured run/agent/state/source/latency logs; Langfuse optional.

Shared run states: `CREATED → INGESTING → ANALYZING → NEEDS_REVIEW → APPROVED → COMPLETED`, with `REJECTED` and `FAILED` branches.

### Business Value

- Reduce repeated patient questioning and manual form transcription.
- Give nurses and clinicians a consistent pre-consultation summary.
- Identify missing information and administrative urgency earlier.
- Route cases to the appropriate specialty or appointment type.
- Preserve the reasoning, consent, and reviewer decisions for auditability.

### Demo Users

- Patient/caregiver
- Nurse or intake coordinator
- Clinician reviewer
- Scheduling/care-navigation coordinator

### End-to-End Flow

1. Start a synthetic patient intake session and capture consent for the demonstration.
2. Collect reason for visit, symptoms, duration, history, allergies, medications, and contact preferences.
3. Ask adaptive follow-up questions only where required information is missing.
4. Normalize patient-reported information into a structured case record.
5. Apply approved low/medium/high administrative priority rules and show the evidence/rule IDs.
6. Recommend department, specialty, appointment type, and next administrative step.
7. Generate a concise clinician-facing summary containing stated facts, missing information, warnings, and source references.
8. Nurse/clinician approves, edits, or rejects the result.
9. Create a draft scheduling/escalation task only after review; record the final disposition and audit trail.

### Agent Responsibilities

| Agent | Input | Typed output |
|---|---|---|
| Intake Agent | User answers and consent | `IntakeSession` with consent/status |
| Question Planner | Partial intake record | `NextQuestion` with reason and required field |
| Symptom/History Extractor | Answers and optional reports | `PatientReportedFacts[]` with source turn |
| Safety/Urgency Evaluator | Facts, configured rules | `TriageResult` with priority, rule IDs, warnings |
| Care Navigator | Triage result, specialty map | `RoutingRecommendation` with rationale |
| Summary Agent | Approved facts and artifacts | `ClinicianSummary` with evidence and missing data |
| Human Review | All recommendations | `ClinicalReview` with approve/edit/reject decision |
| Task/Report Agent | Approved review | `CareTask` and exportable report |

Keep rule-based urgency evaluation separate from LLM-generated explanations. The LLM cannot override a safety rule or suppress a warning.

### Core Data Models

```text
IntakeSession(id, status, consent_status, started_at, completed_at)
PatientCase(id, session_id, demographics_fixture, specialty_hint)
PatientFact(id, case_id, kind, value, source_turn, confidence)
AllergyMedication(id, case_id, kind, name, reaction_or_dose, source_turn)
TriageRule(id, version, priority, condition, action, explanation)
TriageResult(id, case_id, priority, rule_ids, warnings, evidence)
RoutingRecommendation(id, case_id, specialty, appointment_type, rationale)
ClinicalSummary(id, case_id, sections, evidence, missing_information)
ClinicalReview(id, case_id, decision, reviewer_role, edits, created_at)
AuditEvent(id, case_id, actor, action, payload, created_at)
```

### Required Screens

1. Patient/staff intake conversation
2. Intake progress and missing-information state
3. Structured patient-reported facts
4. Priority result with rule evidence and warnings
5. Specialty/appointment recommendation
6. Clinician review and edit screen
7. Draft task/report output
8. Consent and audit timeline

### API Additions

```text
POST /api/v1/healthcare/intake-sessions
POST /api/v1/healthcare/intake-sessions/{id}/messages
GET  /api/v1/healthcare/cases/{case_id}
POST /api/v1/healthcare/cases/{case_id}/triage
POST /api/v1/healthcare/cases/{case_id}/review
GET  /api/v1/healthcare/cases/{case_id}/audit
```

### Fixtures and Evaluation

Create synthetic cases for low, medium, and high administrative priority, plus an incomplete intake and a case with an allergy/medication warning. Use customer-readable but non-clinical demonstration rules. Optional report upload should be limited to text extraction; no real imaging diagnosis is required.

Developer checks:

- consent is captured before the session proceeds;
- adaptive questions stop when required fields are complete;
- every priority result maps to a configured rule and evidence item;
- missing or high-risk information routes to human review;
- no patient-facing recommendation is emitted before approval;
- reviewer edits are preserved separately from original patient statements;
- task creation is a draft-only action;
- a seeded case can be reset and replayed for the demo.

### Three-Week Track

**Week 1:** synthetic cases, schemas, consent/intake flow, specialty map, triage-rule format, intake UI.

**Week 2:** LangGraph workflow, adaptive questions, extraction, triage/routing agents, evidence view, clinician review API.

**Week 3:** summary/task output, audit timeline, seeded demo cases, smoke validation, screenshots/video, technical handoff.

### Explicit Exclusions

Autonomous diagnosis, treatment recommendations, medication prescribing, emergency-care decisions, live EMR/HIS/FHIR write-back, real PHI, medical imaging interpretation, real appointment booking, client deployment, and clinical validation/certification.

### Future Extension

If a healthcare prospect needs a deeper clinical workflow later, this POC can grow into a human-supervised CDSS with report processing, chest-X-ray or lab-model adapters, allergy/interaction checks, additional diagnostic suggestions, FHIR interoperability, and hospital resource coordination. Those extensions require separate clinical governance and validation.
