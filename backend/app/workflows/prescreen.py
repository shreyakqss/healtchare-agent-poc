"""Pre-screening: records -> urgency (rules) -> routing -> summary -> NEEDS_REVIEW."""

from __future__ import annotations

import logging
import uuid

from agno.run.base import RunStatus
from agno.workflow import Step, Workflow
from agno.workflow.types import StepInput, StepOutput

from app.agents import AgentUnavailable
from app.agents.summary_writer import SummaryInputs, write_prescreening
from app.db import db_session
from app.domain import routing as routing_rules
from app.domain import triage_engine
from app.domain.lifecycle import CaseStatus
from app.integrations.hms import get_hms
from app.models import ClinicalSummary, RoutingRecommendation, TriageResult
from app.services import audit, case_repo, hospital_config, lifecycle, triage_rules
from app.workflows.common import case_id_from

logger = logging.getLogger(__name__)


async def collect_records(step_input: StepInput) -> StepOutput:
    case_id = case_id_from(step_input)
    with db_session() as db:
        docs, images = [], []
        for a in case_repo.attachments(db, case_id):
            if a.extracted_text:
                docs.append({"filename": a.filename, "kind": a.kind, "excerpt": a.extracted_text[:1500]})
            else:
                images.append({"filename": a.filename, "kind": a.kind})
        audit.record(db, case_id, "system:record_processor", "records.processed",
                     {"documents": len(docs), "images": len(images), "interpreted": False})
    return StepOutput(content={"documents": docs, "images": images})


async def evaluate_urgency(step_input: StepInput) -> StepOutput:
    """Zero LLM calls. Every priority traces to a TriageRule row and an evidence item."""
    case_id = case_id_from(step_input)
    with db_session() as db:
        case = case_repo.case_or_404(db, case_id)
        outcome = triage_engine.evaluate(
            case_repo.facts(db, case_id),
            case_repo.clinical_entries(db, case_id),
            triage_rules.active_rules(db, case.hospital_id),
        )
        db.add(TriageResult(
            case_id=case_id, priority=outcome.priority, rule_ids=outcome.rule_ids,
            rule_codes=outcome.rule_codes, warnings=outcome.warnings, evidence=outcome.evidence,
        ))
        audit.record(db, case_id, "system:urgency_evaluator", "triage.evaluated",
                     {"priority": outcome.priority, "rule_codes": outcome.rule_codes, "warnings": len(outcome.warnings)})
    return StepOutput(content={"priority": outcome.priority, "specialty_hint": outcome.specialty_hint, "rule_codes": outcome.rule_codes})


async def navigate_care(step_input: StepInput) -> StepOutput:
    case_id = case_id_from(step_input)
    urgency = step_input.get_step_content("evaluate_urgency") or {}
    with db_session() as db:
        case = case_repo.case_or_404(db, case_id)
        decision = routing_rules.route(
            case_repo.facts(db, case_id), hospital_config.load(), urgency["priority"], urgency.get("specialty_hint"),
        )
        slots = get_hms().available_slots(decision.department["id"], decision.doctor["id"] if decision.doctor else None, limit=1)
        slot = slots[0].model_dump(mode="json") if slots else None
        db.add(RoutingRecommendation(
            case_id=case_id,
            department_id=decision.department["id"], department_name=decision.department["name"],
            doctor_id=decision.doctor["id"] if decision.doctor else None,
            doctor_name=decision.doctor["name"] if decision.doctor else None,
            appointment_type_id=decision.appointment_type["id"], appointment_type_label=decision.appointment_type["label"],
            rationale=decision.rationale, matched_keywords=decision.matched_keywords, suggested_slot=slot,
        ))
        case.specialty_hint = decision.department["id"]
        audit.record(db, case_id, "system:care_navigator", "routing.recommended",
                     {"department_id": decision.department["id"], "doctor_id": decision.doctor["id"] if decision.doctor else None,
                      "appointment_type": decision.appointment_type["id"], "basis": decision.basis, "hms_slot": slot["id"] if slot else None})
    return StepOutput(content={"department": decision.department["name"]})


def _plain_sections(facts, entries) -> dict:
    return {
        "chief_complaint": next((f.value for f in facts if f.kind == "reason_for_visit"), "Not recorded"),
        "reported_symptoms": [f.value for f in facts if f.kind == "symptom"],
        "relevant_history": [f.value for f in facts if f.kind in {"history", "condition"}],
        "medications": [e.name for e in entries if e.kind == "medication"],
        "allergies": [e.name for e in entries if e.kind == "allergy"],
        "missing_information": [],
        "context_for_clinician": "Direct listing of recorded facts. No narrative summary was generated for this case.",
    }


async def write_summary(step_input: StepInput) -> StepOutput:
    case_id = case_id_from(step_input)
    records = step_input.get_step_content("collect_records") or {}
    with db_session() as db:
        case = case_repo.case_or_404(db, case_id)
        facts = case_repo.facts(db, case_id)
        entries = case_repo.clinical_entries(db, case_id)
        hms_patient = get_hms().get_patient(case.hms_patient_id) if case.hms_patient_id else None
        inputs = SummaryInputs(
            facts=[(f.kind, f.value) for f in facts],
            entries=[(e.kind, e.name, e.reaction_or_dose or "") for e in entries],
            documents=[(d["filename"], d["excerpt"]) for d in records.get("documents", [])],
            images=[i["filename"] for i in records.get("images", [])],
            hms_record=hms_patient.model_dump(mode="json", exclude={"phone"}) if hms_patient else None,
        )
        try:
            sections = (await write_prescreening(inputs)).model_dump()
            generated_by = "llm"
        except AgentUnavailable as exc:
            logger.warning("Summary writer unavailable: %s", exc)
            sections, generated_by = _plain_sections(facts, entries), "fallback"

        missing = list(sections.get("missing_information", []))
        for field in case_repo.missing_fields(db, case_id):
            label = f"Required intake field not collected: {field.replace('_', ' ')}"
            if label not in missing:
                missing.append(label)
        sections["missing_information"] = missing
        sections["attachments"] = {"documents": [{k: v for k, v in d.items() if k != "excerpt"} for d in records.get("documents", [])],
                                   "images": records.get("images", [])}

        triage = case_repo.latest_triage(db, case_id)
        db.add(ClinicalSummary(
            case_id=case_id, kind="prescreening", sections=sections,
            evidence=list(triage.evidence) if triage else [], missing_information=missing, generated_by=generated_by,
        ))
        audit.record(db, case_id, "system:summary_writer", "summary.prescreening_generated",
                     {"generated_by": generated_by, "missing_information": len(missing)})
    return StepOutput(content={"generated_by": generated_by, "missing": len(missing)})


async def mark_needs_review(step_input: StepInput) -> StepOutput:
    case_id = case_id_from(step_input)
    with db_session() as db:
        case = case_repo.case_or_404(db, case_id)
        session = case_repo.session_for(db, case)
        lifecycle.transition(db, session, CaseStatus.NEEDS_REVIEW, "system:prescreen", case_id)
    return StepOutput(content={"status": CaseStatus.NEEDS_REVIEW})


prescreen_workflow = Workflow(
    name="prescreen",
    description="Rule-based urgency, routing and clinician briefing. Ends at NEEDS_REVIEW.",
    steps=[
        Step(name="collect_records", executor=collect_records),
        Step(name="evaluate_urgency", executor=evaluate_urgency),
        Step(name="navigate_care", executor=navigate_care),
        Step(name="write_summary", executor=write_summary),
        Step(name="mark_needs_review", executor=mark_needs_review),
    ],
    telemetry=False,
)


async def run_prescreen(case_id: uuid.UUID) -> None:
    with db_session() as db:
        case = case_repo.case_or_404(db, case_id)
        session = case_repo.session_for(db, case)
        lifecycle.transition(db, session, CaseStatus.ANALYZING, "system:prescreen", case_id)
    try:
        result = await prescreen_workflow.arun(input={"case_id": str(case_id)})
        if result.status != RunStatus.completed:
            raise RuntimeError(f"Workflow ended with status {result.status}: {result.content}")
    except Exception as exc:
        logger.exception("Prescreen failed for %s", case_id)
        with db_session() as db:
            case = case_repo.case_or_404(db, case_id)
            session = case_repo.session_for(db, case)
            audit.record(db, case_id, "system:prescreen", "workflow.failed", {"error": str(exc)[:500]})
            lifecycle.transition(db, session, CaseStatus.FAILED, "system:prescreen", case_id)
        raise