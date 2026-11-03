"""AI help with the consultation report. Drafts and edit proposals go back to the doctor's form
only - nothing is stored until the doctor saves the consultation with their HMS password
(consultation_service.record_note), which also records which sections were still AI-written.
Drafting is open from review onwards so the doctor can prepare the report while reviewing;
saving it stays behind the review gate."""

from __future__ import annotations

import re
import uuid

from sqlalchemy.orm import Session

from app.agents import report_writer
from app.core.errors import Conflict
from app.domain.lifecycle import CaseStatus
from app.models import ClinicalSummary
from app.services import audit, case_repo, doctor_assistant_service

SECTIONS = ("history", "examination", "diagnosis", "investigations", "prescription", "advice", "referral")


def accepted_diagnoses(db: Session, case_id: uuid.UUID) -> list[str]:
    summary = case_repo.summary(db, case_id, "ai_diagnosis")
    if summary is None:
        return []
    decisions = summary.sections.get("decisions", {})
    out = []
    for i, d in enumerate(summary.sections.get("differentials", [])):
        decision = decisions.get(str(i), {})
        if decision.get("decision") in {"accept", "edit"}:
            out.append(decision.get("text") or d["condition"])
    return out


DRAFTABLE = {CaseStatus.NEEDS_REVIEW, CaseStatus.APPROVED}


def _require_draftable(db: Session, case_id: uuid.UUID) -> None:
    status = case_repo.session_for(db, case_repo.case_or_404(db, case_id)).status
    if status not in DRAFTABLE:
        raise Conflict(f"A report can be drafted after pre-screening and until it is released (status is {status}).")


DRAFT_KIND = "report_draft"

_TABLE_RULE = re.compile(r"^\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?$")
_LIST_MARK = re.compile(r"^(?:[-*•]\s+|\d+[.)]\s+|#+\s*)")


def plain_text(text: str) -> str:
    """The report is printed as plain lines on the letterhead; the model sometimes answers in
    markdown anyway. Tables become one cell-row per line (header row dropped), and list marks,
    headings and emphasis are removed."""
    lines: list[str] = []
    rows = [line.strip() for line in text.strip().splitlines()]
    for i, line in enumerate(rows):
        if _TABLE_RULE.match(line):
            continue
        if line.startswith("|"):
            if i + 1 < len(rows) and _TABLE_RULE.match(rows[i + 1]):
                continue  # a table's header row
            line = ", ".join(cell.strip() for cell in line.strip("|").split("|") if cell.strip())
        line = _LIST_MARK.sub("", line).replace("**", "").replace("__", "")
        if line or (lines and lines[-1]):
            lines.append(line)
    return "\n".join(lines).strip()


async def write_draft(db: Session, case_id: uuid.UUID, actor: str) -> dict[str, str]:
    """Draft the report and keep it on the case (ClinicalSummary `report_draft`) so the doctor's
    form opens already filled in. A draft, never the report: clinician-facing only, and the signed
    ConsultationNote is what reaches the patient. Raises AgentUnavailable when the model is down."""
    result = await report_writer.draft(doctor_assistant_service.case_context(db, case_id), accepted_diagnoses(db, case_id))
    sections = {k: plain_text(v) for k, v in result.model_dump().items()} | {"examination": ""}
    db.add(ClinicalSummary(case_id=case_id, kind=DRAFT_KIND, sections=sections, generated_by="llm"))
    audit.record(db, case_id, actor, "report.ai_drafted", {})
    db.commit()
    return sections


async def draft(db: Session, case_id: uuid.UUID, actor: str) -> dict[str, str]:
    _require_draftable(db, case_id)
    return await write_draft(db, case_id, actor)


async def propose_edit(
    db: Session, case_id: uuid.UUID, sections: dict[str, str], instruction: str, actor: str,
) -> dict:
    """Raises AgentUnavailable when the model is down."""
    _require_draftable(db, case_id)
    current = {k: sections.get(k, "") for k in SECTIONS}
    proposal = await report_writer.edit(doctor_assistant_service.case_context(db, case_id), current, instruction)
    for e in proposal.edits:
        e.text = plain_text(e.text)
    audit.record(db, case_id, actor, "report.ai_edit_proposed", {"sections": [e.section for e in proposal.edits]})
    db.commit()
    return proposal.model_dump()
