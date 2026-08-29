"""Shared plumbing for the agno workflows."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from agno.workflow import Step
from agno.workflow.types import StepInput, StepOutput
from sqlalchemy.orm import Session

from app.services import workflow_operations

StepExecutor = Callable[[StepInput], Awaitable[StepOutput]]


def step(name: str, executor: StepExecutor) -> Step:
    """A workflow step that fails the run when it fails.

    agno's `Step` defaults to `on_error="skip"` and three retries: a step that raises is
    silently skipped and the workflow still reports `completed`. For these workflows that
    would mean a case reaching NEEDS_REVIEW without a routing recommendation, or COMPLETED
    without a care task. Every step here opens its own `db_session()` (rolled back on error)
    and every agent call already degrades to a documented fallback, so a raise is a real
    failure: surface it, let `run_*` mark the case FAILED and audit the reason.
    """
    return Step(name=name, executor=executor, on_error="fail", max_retries=0)


def case_id_from(step_input: StepInput) -> uuid.UUID:
    raw: Any = step_input.input
    if isinstance(raw, dict):
        return uuid.UUID(str(raw["case_id"]))
    return uuid.UUID(str(raw))


def workflow_input(step_input: StepInput) -> dict[str, Any]:
    """The full workflow `input` dict (case_id plus any extra context, e.g. finalize's
    verified finalizer identity). Falls back to an empty dict when `input` wasn't a dict
    (case_id-only invocations)."""
    raw: Any = step_input.input
    return raw if isinstance(raw, dict) else {}


def step_operation_key(step_input: StepInput, name: str) -> str | None:
    job_id = workflow_input(step_input).get("job_id")
    return f"job:{job_id}:step:{name}" if job_id else None


def completed_step(db: Session, step_input: StepInput, name: str) -> dict[str, Any] | None:
    return workflow_operations.completed_result(db, step_operation_key(step_input, name))


def complete_step(
    db: Session,
    step_input: StepInput,
    name: str,
    result: dict[str, Any],
) -> None:
    workflow_operations.complete(
        db,
        case_id_from(step_input),
        step_operation_key(step_input, name),
        f"workflow_step.{name}",
        result,
    )
