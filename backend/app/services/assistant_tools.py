"""Resolve one scoped, read-only reference for a patient question."""

from __future__ import annotations

import json
import uuid

from sqlalchemy.orm import Session

from app.agents.schemas import QuestionScope
from app.agents.tools.web_search import search_health_information
from app.core.config import settings
from app.domain import intake_fields
from app.services import case_repo, hospital_config
from app.services.attachments import kind_label

MAX_DOCUMENTS = 4
MAX_DOCUMENT_CHARS = 3000
CLINICAL_FACT_KINDS = {"reason_for_visit", "symptom", "duration", "history"}


async def resolve(
    db: Session,
    case_id: uuid.UUID,
    scope: QuestionScope,
    health_topic: str | None = None,
) -> str | None:
    if scope == "personal_record":
        documents = [
            {
                "kind": kind_label(row.kind),
                "filename": row.filename,
                "text": (row.extracted_text or "").strip()[:MAX_DOCUMENT_CHARS] or None,
            }
            for row in case_repo.attachments(db, case_id)[-MAX_DOCUMENTS:]
        ]
        facts = [
            {"kind": fact.kind, "value": fact.value}
            for fact in case_repo.facts(db, case_id)
            if fact.kind in CLINICAL_FACT_KINDS and fact.value not in intake_fields.PLACEHOLDERS
        ]
        entries = [
            {"kind": entry.kind, "name": entry.name, "detail": entry.reaction_or_dose}
            for entry in case_repo.clinical_entries(db, case_id)
        ]
        return json.dumps({"documents": documents, "intake": facts, "medications_allergies": entries})
    if scope == "clinic":
        return json.dumps(
            {
                "clinic": hospital_config.hospital().get("name", ""),
                "departments": [department["name"] for department in hospital_config.departments()],
                "appointment_types": [item["label"] for item in hospital_config.appointment_types()],
            }
        )
    if scope == "general_health":
        if settings.TAVILY_API_KEY and health_topic:
            return await search_health_information(health_topic)
        return json.dumps({"topic": health_topic, "results": []})
    return None
