"""Summary Agent — the clinician-facing pre-screening overview.

The LLM writes prose here, but only over facts that are already in the
database. The priority and its rule evidence are copied through verbatim from
the TriageResult — the model is never asked to judge urgency, and its output is
never allowed to replace what the rule engine decided.
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from agents.medical_record_processor import collect_attachments
from agents.question_planner import missing_fields
from models import (
    AllergyMedication,
    AuditEvent,
    ClinicalSummary,
    PatientFact,
    TriageResult,
)
from schemas.agent_outputs import PrescreeningSummary, json_schema
from services.llm_client import LLMError, llm

logger = logging.getLogger(__name__)

SYSTEM = """You prepare a pre-consultation briefing for a clinician from patient-reported \
intake information.

You are a documentation assistant, not a diagnostician. Absolute rules:
- Summarise only what the patient stated. Never infer a diagnosis.
- Never suggest treatment, medication, or tests.
- Never state or imply how urgent the case is — urgency is decided elsewhere.
- Never interpret an uploaded image or report; you may quote extracted text.
- If information is missing, list it under missing_information rather than \
guessing at it.

Write in neutral clinical-administrative language."""


def _fact_lines(facts: list[PatientFact]) -> str:
    if not facts:
        return "(none recorded)"
    return "\n".join(f"- [{f.kind}] {f.value}" for f in facts)


def build_plain_sections(
    facts: list[PatientFact], entries: list[AllergyMedication]
) -> dict:
    """A structured listing of recorded facts, with no narrative generation.

    Used when the language model is unavailable, and by the seed script so
    demo data can be generated without Ollama running.
    """
    return {
        "chief_complaint": next(
            (f.value for f in facts if f.kind == "reason_for_visit"), "Not recorded"
        ),
        "reported_symptoms": [f.value for f in facts if f.kind == "symptom"],
        "relevant_history": [
            f.value for f in facts if f.kind in {"history", "condition"}
        ],
        "medications": [e.name for e in entries if e.kind == "medication"],
        "allergies": [e.name for e in entries if e.kind == "allergy"],
        "context_for_clinician": (
            "Direct listing of patient-reported facts. No narrative summary was "
            "generated for this case."
        ),
        "missing_information": [],
    }


async def summarise_prescreening(db: Session, case_id) -> ClinicalSummary:
    facts = db.query(PatientFact).filter(PatientFact.case_id == case_id).all()
    entries = (
        db.query(AllergyMedication)
        .filter(AllergyMedication.case_id == case_id)
        .all()
    )
    triage = (
        db.query(TriageResult)
        .filter(TriageResult.case_id == case_id)
        .order_by(TriageResult.created_at.desc())
        .first()
    )
    attachments = collect_attachments(db, case_id)

    allergy_lines = "\n".join(
        f"- [{e.kind}] {e.name}"
        + (f" ({e.reaction_or_dose})" if e.reaction_or_dose else "")
        for e in entries
    ) or "(none recorded)"

    document_lines = "\n".join(
        f"- {d['kind']}: {d['filename']}\n  extracted text: {d['excerpt'][:600]}"
        for d in attachments["documents"]
    ) or "(no document text)"

    image_lines = "\n".join(
        f"- {i['kind']}: {i['filename']} (image, not interpreted)"
        for i in attachments["images_and_unparsed"]
    ) or "(no images)"

    user = f"""Patient-reported facts:
{_fact_lines(facts)}

Allergies and medications:
{allergy_lines}

Uploaded documents (extracted text only):
{document_lines}

Uploaded images (listed for the clinician; do not describe them):
{image_lines}

Produce the pre-screening briefing."""

    try:
        raw = await llm.chat_json(SYSTEM, user, json_schema(PrescreeningSummary))
        summary = PrescreeningSummary.model_validate(raw)
        sections = summary.model_dump()
        missing = summary.missing_information
    except (LLMError, ValueError) as exc:
        # Degrade to a structured dump rather than blocking the clinician.
        logger.warning("Summary agent fell back to a plain listing: %s", exc)
        sections = build_plain_sections(facts, entries)
        missing = []

    # Merge in the gaps computed from the required-field list. The model may or
    # may not notice them; this is the check that actually routes an incomplete
    # intake to a clinician.
    outstanding = missing_fields(db, case_id)
    for field in outstanding:
        label = f"Required intake field not collected: {field.replace('_', ' ')}"
        if label not in missing:
            missing.append(label)
    sections["missing_information"] = missing

    sections["attachments"] = {
        "documents": [
            {k: v for k, v in d.items() if k != "excerpt"}
            for d in attachments["documents"]
        ],
        "images_and_unparsed": attachments["images_and_unparsed"],
    }

    # Priority and evidence are copied from the rule engine, not authored here.
    evidence = list(triage.evidence or []) if triage else []
    if triage:
        sections["administrative_priority"] = triage.priority
        sections["priority_warnings"] = triage.warnings or []

    record = ClinicalSummary(
        case_id=case_id,
        kind="prescreening",
        sections=sections,
        evidence=evidence,
        missing_information=missing,
    )
    db.add(record)
    db.add(
        AuditEvent(
            case_id=case_id,
            actor="system:summary_agent",
            action="summary.prescreening_generated",
            payload={"missing_information_count": len(missing)},
        )
    )
    db.commit()
    db.refresh(record)
    return record
