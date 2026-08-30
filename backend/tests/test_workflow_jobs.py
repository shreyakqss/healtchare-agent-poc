import asyncio
import uuid
from datetime import timedelta

import pytest

from app.db import SessionLocal, utcnow
from app.models import IntakeSession, PatientCase, WorkflowJob, WorkflowOperation
from app.services import workflow_jobs, workflow_operations


@pytest.fixture
def case_id():
    with SessionLocal() as db:
        session = IntakeSession(status="ANALYZING", consent_status="GRANTED", channel="web")
        db.add(session)
        db.flush()
        case = PatientCase(
            session_id=session.id,
            hospital_id="qss-demo-clinic",
        )
        db.add(case)
        db.commit()
        value = case.id
    yield value
    with SessionLocal() as db:
        case = db.get(PatientCase, value)
        if case is not None:
            db.delete(case)
            db.commit()


def test_enqueue_is_idempotent_and_only_one_worker_claims(case_id):
    with SessionLocal() as db:
        first = workflow_jobs.enqueue(db, case_id, "prescreen")
        second = workflow_jobs.enqueue(db, case_id, "prescreen")
        db.commit()
        assert first.id == second.id
        claimed = workflow_jobs._claim(db, "worker-a", first.id)
        assert claimed is not None and claimed.case_id == case_id
        assert workflow_jobs._claim(db, "worker-b", first.id) is None


def test_expired_lease_is_recovered(case_id):
    with SessionLocal() as db:
        job = workflow_jobs.enqueue(db, case_id, "prescreen")
        job.status = "running"
        job.locked_by = "dead-worker"
        job.lease_expires_at = utcnow() - timedelta(seconds=1)
        db.commit()

        recovered = workflow_jobs._claim(db, "replacement-worker", job.id)
        assert recovered is not None
        assert recovered.locked_by == "replacement-worker"
        assert recovered.attempt_count == 1


def test_failed_job_requeues_then_succeeds(case_id, monkeypatch):
    calls = 0

    async def failing_once(case_id, *, job_id=None, mark_failed=True):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise ConnectionError("synthetic failure")

    monkeypatch.setattr(workflow_jobs, "run_prescreen", failing_once)
    with SessionLocal() as db:
        job_id = workflow_jobs.enqueue(db, case_id, "prescreen", max_attempts=2).id
        db.commit()

    with SessionLocal() as db:
        first = workflow_jobs._claim(db, "worker-a", job_id)
    asyncio.run(workflow_jobs.execute(first, "worker-a"))
    with SessionLocal() as db:
        job = db.get(WorkflowJob, job_id)
        assert job.status == "queued"
        job.available_at = utcnow()
        db.commit()

    with SessionLocal() as db:
        second = workflow_jobs._claim(db, "worker-b", job_id)
    asyncio.run(workflow_jobs.execute(second, "worker-b"))
    with SessionLocal() as db:
        job = db.get(WorkflowJob, job_id)
        assert job.status == "succeeded"
        assert job.attempt_count == 2


def test_operation_checkpoint_returns_committed_result(case_id):
    key = f"case:{case_id}:test-operation"
    with SessionLocal() as db:
        assert workflow_operations.completed_result(db, key) is None
        workflow_operations.complete(db, case_id, key, "test", {"reference": "ref-1"})
        db.commit()
    with SessionLocal() as db:
        assert workflow_operations.completed_result(db, key) == {"reference": "ref-1"}
        assert db.query(WorkflowOperation).filter_by(operation_key=key).count() == 1


def test_finishing_a_concurrently_deleted_job_is_a_noop():
    assert workflow_jobs._finish(uuid.uuid4(), "worker-a", "RuntimeError") is False
