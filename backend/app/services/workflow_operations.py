from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.db import utcnow
from app.models import WorkflowOperation


def completed_result(db: Session, operation_key: str | None) -> dict[str, Any] | None:
    if not operation_key:
        return None
    row = db.query(WorkflowOperation).filter(WorkflowOperation.operation_key == operation_key).first()
    return dict(row.result) if row is not None and row.status == "succeeded" else None


def complete(
    db: Session,
    case_id: uuid.UUID,
    operation_key: str | None,
    kind: str,
    result: dict[str, Any],
) -> None:
    if not operation_key:
        return
    row = db.query(WorkflowOperation).filter(WorkflowOperation.operation_key == operation_key).first()
    if row is None:
        row = WorkflowOperation(case_id=case_id, operation_key=operation_key, kind=kind)
        db.add(row)
    row.status = "succeeded"
    row.result = result
    row.last_error_code = None
    row.completed_at = utcnow()


def begin_external(
    db: Session,
    case_id: uuid.UUID,
    operation_key: str,
    kind: str,
) -> tuple[WorkflowOperation, bool]:
    row = db.query(WorkflowOperation).filter(WorkflowOperation.operation_key == operation_key).first()
    if row is None:
        row = WorkflowOperation(case_id=case_id, operation_key=operation_key, kind=kind)
        db.add(row)
    if row.status == "succeeded":
        return row, True
    row.status = "pending"
    row.attempt_count = (row.attempt_count or 0) + 1
    row.last_error_code = None
    db.commit()
    return row, False


def finish_external(
    db: Session,
    row: WorkflowOperation,
    *,
    result: dict[str, Any] | None = None,
    error_code: str | None = None,
) -> None:
    row.status = "succeeded" if error_code is None else "failed"
    row.result = result or {}
    row.last_error_code = error_code
    row.completed_at = utcnow() if error_code is None else None
    db.commit()
