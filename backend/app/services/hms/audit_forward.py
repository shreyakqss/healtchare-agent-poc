"""Best-effort mirror of local audit events onto the linked HMS record.

The local `AuditEvent` table stays the source of truth. OpenEMR's registered client has
no `AuditEvent` write scope, so a short human-readable note is pushed as a
`DocumentReference` through the same `push_document` path used for approved summaries.
"""

from __future__ import annotations

import logging
from typing import Any

from app.db.base import utcnow
from app.integrations.hms import get_hms
from app.models import PatientCase

logger = logging.getLogger(__name__)

AUDIT_NOTE_TITLE = "CareFlow Audit Note"


def render_audit_note(actor: str, action: str, payload: dict[str, Any]) -> str:
    details = ", ".join(f"{k}={v!r}" for k, v in sorted(payload.items())) or "(none)"
    return (
        "CareFlow audit note\n"
        f"Timestamp: {utcnow().isoformat()}\n"
        f"Actor: {actor}\n"
        f"Action: {action}\n"
        f"Details: {details}\n"
    )


def forward_audit_note(case: PatientCase, actor: str, action: str, payload: dict[str, Any]) -> None:
    """Skips silently when the case has no HMS link; never raises."""
    if not case.hms_patient_id:
        return
    try:
        get_hms().push_document(
            case.hms_patient_id, title=AUDIT_NOTE_TITLE,
            content=render_audit_note(actor, action, payload).encode("utf-8"), content_type="text/plain",
        )
    except Exception as exc:  # noqa: BLE001 - a mirror must never break the primary write
        logger.warning("Audit forward to HMS failed (%s)", type(exc).__name__)
