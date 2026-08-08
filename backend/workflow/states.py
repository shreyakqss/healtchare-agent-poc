"""Shared state passed between graph nodes.

Deliberately small: the durable record lives in Postgres, and this carries only
what one graph run needs to hand from node to node. Nothing here is the source
of truth — if a value matters after the run, a node has already written it to a
table.
"""

from __future__ import annotations

from typing import Any, TypedDict

# Documented lifecycle from PROJECT_FOUNDATION.md.
RUN_STATES = (
    "CREATED",
    "INGESTING",
    "ANALYZING",
    "NEEDS_REVIEW",
    "APPROVED",
    "COMPLETED",
    "REJECTED",
    "FAILED",
)


class CaseState(TypedDict, total=False):
    session_id: str
    case_id: str
    status: str

    # intake turn
    last_message: str
    turn_index: int
    transcript: list[dict[str, str]]
    next_question: str
    missing_fields: list[str]
    intake_complete: bool
    # Which required field `next_question` is asking about, stored on the
    # message so the next turn can recognise a denial.
    asks_field: str
    extracted: dict[str, int]

    # pre-screening
    attachments: dict[str, Any]
    priority: str
    rule_codes: list[str]
    warnings: list[dict[str, Any]]
    specialty_hint: str | None
    department_id: str | None
    doctor_id: str | None
    summary_id: str

    # finalisation
    draft_task: dict[str, Any]

    error: str
