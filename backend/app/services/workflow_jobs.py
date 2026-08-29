from __future__ import annotations

import asyncio
import logging
import os
import socket
import uuid
from contextlib import suppress
from datetime import timedelta
from typing import Any

from sqlalchemy import and_, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import Conflict
from app.db import db_session, utcnow
from app.domain.lifecycle import CaseStatus, IllegalTransition
from app.models import WorkflowJob
from app.services import audit, case_repo, lifecycle
from app.workflows import run_finalize, run_prescreen

logger = logging.getLogger(__name__)


def _operation_key(workflow: str, case_id: uuid.UUID) -> str:
    return f"{workflow}:{case_id}:v1"


def enqueue(
    db: Session,
    case_id: uuid.UUID,
    workflow: str,
    *,
    payload: dict[str, Any] | None = None,
    max_attempts: int | None = None,
) -> WorkflowJob:
    key = _operation_key(workflow, case_id)
    job = db.query(WorkflowJob).filter(WorkflowJob.operation_key == key).first()
    if job is not None:
        return job
    job = WorkflowJob(
        case_id=case_id,
        workflow=workflow,
        operation_key=key,
        payload=payload or {},
        max_attempts=max_attempts or settings.WORKFLOW_MAX_ATTEMPTS,
    )
    try:
        with db.begin_nested():
            db.add(job)
            db.flush()
    except IntegrityError:
        job = db.query(WorkflowJob).filter(WorkflowJob.operation_key == key).one()
        return job
    audit.record(db, case_id, "system:workflow", "workflow.queued", {"workflow": workflow})
    return job


def _eligible(now):
    return or_(
        and_(WorkflowJob.status == "queued", WorkflowJob.available_at <= now),
        and_(WorkflowJob.status == "running", WorkflowJob.lease_expires_at < now),
    )


def _claim(db: Session, worker_id: str, job_id: uuid.UUID | None = None) -> WorkflowJob | None:
    now = utcnow()
    statement = select(WorkflowJob).where(_eligible(now)).order_by(WorkflowJob.available_at, WorkflowJob.created_at)
    if job_id is not None:
        statement = statement.where(WorkflowJob.id == job_id)
    job = db.execute(statement.with_for_update(skip_locked=True).limit(1)).scalar_one_or_none()
    if job is None:
        return None
    recovered = job.status == "running"
    job.status = "running"
    job.locked_by = worker_id
    job.lease_expires_at = now + timedelta(seconds=settings.WORKFLOW_LEASE_SECONDS)
    job.attempt_count += 1
    if recovered:
        audit.record(db, job.case_id, "system:workflow", "workflow.lease_recovered", {"workflow": job.workflow})
    db.commit()
    return job


def claim_next(worker_id: str) -> WorkflowJob | None:
    with db_session() as db:
        return _claim(db, worker_id)


def _mark_failed_case(case_id: uuid.UUID, workflow: str, error_code: str) -> None:
    with db_session() as db:
        case = case_repo.case_or_404(db, case_id)
        session = case_repo.session_for(db, case)
        audit.record(
            db,
            case_id,
            "system:workflow",
            "workflow.failed",
            {"workflow": workflow, "error_type": error_code, "attempts_exhausted": True},
        )
        try:
            lifecycle.transition(db, session, CaseStatus.FAILED, "system:workflow", case_id, commit=False)
        except IllegalTransition:
            logger.warning("Could not mark exhausted %s job failed from status %s", workflow, session.status)


def _finish(job_id: uuid.UUID, worker_id: str, error_code: str | None) -> bool:
    exhausted = False
    case_id: uuid.UUID | None = None
    workflow = ""
    with db_session() as db:
        job = db.execute(
            select(WorkflowJob).where(WorkflowJob.id == job_id).with_for_update()
        ).scalar_one_or_none()
        if job is None:
            return False
        if job.status != "running" or job.locked_by != worker_id:
            return False
        case_id, workflow = job.case_id, job.workflow
        job.locked_by = None
        job.lease_expires_at = None
        job.last_error_code = error_code
        if error_code is None:
            job.status = "succeeded"
            job.completed_at = utcnow()
            job.payload = {}
            audit.record(db, job.case_id, "system:workflow", "workflow.succeeded", {"workflow": job.workflow})
        elif job.attempt_count >= job.max_attempts:
            job.status = "failed"
            exhausted = True
        else:
            job.status = "queued"
            job.available_at = utcnow() + timedelta(seconds=min(2 ** job.attempt_count, 30))
            audit.record(
                db,
                job.case_id,
                "system:workflow",
                "workflow.retry_scheduled",
                {"workflow": job.workflow, "attempt": job.attempt_count, "error_type": error_code},
            )
    if exhausted and case_id is not None:
        _mark_failed_case(case_id, workflow, error_code or "UnknownError")
    return exhausted


def _renew_lease(job_id: uuid.UUID, worker_id: str) -> None:
    with db_session() as db:
        job = db.get(WorkflowJob, job_id)
        if job is not None and job.status == "running" and job.locked_by == worker_id:
            job.lease_expires_at = utcnow() + timedelta(seconds=settings.WORKFLOW_LEASE_SECONDS)


async def _heartbeat(job_id: uuid.UUID, worker_id: str) -> None:
    interval = max(1.0, min(settings.WORKFLOW_LEASE_SECONDS / 3, 30.0))
    while True:
        await asyncio.sleep(interval)
        await asyncio.to_thread(_renew_lease, job_id, worker_id)


async def execute(job: WorkflowJob, worker_id: str, *, propagate: bool = False) -> None:
    heartbeat = asyncio.create_task(_heartbeat(job.id, worker_id))
    try:
        if job.workflow == "prescreen":
            await run_prescreen(job.case_id, job_id=job.id, mark_failed=False)
        elif job.workflow == "finalize":
            await run_finalize(
                job.case_id,
                finalizer_id=job.payload.get("finalizer_id"),
                finalizer_name=job.payload.get("finalizer_name"),
                job_id=job.id,
                mark_failed=False,
            )
        else:
            raise RuntimeError(f"Unknown workflow {job.workflow!r}")
    except Exception as exc:
        _finish(job.id, worker_id, type(exc).__name__)
        if propagate:
            raise
        logger.error("Workflow job failed (%s)", type(exc).__name__)
    else:
        _finish(job.id, worker_id, None)
    finally:
        heartbeat.cancel()
        with suppress(asyncio.CancelledError):
            await heartbeat


async def run_now(
    workflow: str,
    case_id: uuid.UUID,
    *,
    payload: dict[str, Any] | None = None,
    max_attempts: int | None = None,
) -> None:
    worker_id = f"request:{uuid.uuid4().hex}"
    with db_session() as db:
        job = enqueue(db, case_id, workflow, payload=payload, max_attempts=max_attempts)
        if job.status == "succeeded":
            return
        claimed = _claim(db, worker_id, job.id)
        if claimed is None:
            raise Conflict(f"{workflow.title()} is already in progress.")
    await execute(claimed, worker_id, propagate=True)


async def run_worker(stop: asyncio.Event) -> None:
    worker_id = f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"
    logger.info("Workflow worker started (%s)", worker_id)
    while not stop.is_set():
        job = await asyncio.to_thread(claim_next, worker_id)
        if job is not None:
            await execute(job, worker_id)
            continue
        try:
            await asyncio.wait_for(stop.wait(), timeout=settings.WORKFLOW_POLL_SECONDS)
        except TimeoutError:
            pass
    logger.info("Workflow worker stopped (%s)", worker_id)
