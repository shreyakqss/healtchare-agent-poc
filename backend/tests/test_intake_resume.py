import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app
from app.models import ApplicationUser, CaseOwner, IntakeSession, PatientCase
from app.security import CurrentPrincipal, authenticate
from app.services import intake_service
from tests.helpers import BASE


@pytest.fixture
def owner_id():
    value = uuid.uuid4()
    with SessionLocal() as db:
        db.add(
            ApplicationUser(
                id=value,
                issuer="https://issuer.test/realms/careflow",
                subject=str(value),
                roles=["patient"],
                active=True,
            )
        )
        db.commit()
    yield value
    with SessionLocal() as db:
        session_ids = [
            row[0]
            for row in (
                db.query(PatientCase.session_id)
                .join(CaseOwner, CaseOwner.case_id == PatientCase.id)
                .filter(CaseOwner.user_id == value)
                .all()
            )
        ]
        db.query(IntakeSession).filter(IntakeSession.id.in_(session_ids)).delete(synchronize_session=False)
        db.delete(db.get(ApplicationUser, value))
        db.commit()


def _start(owner_id: uuid.UUID) -> tuple[str, str]:
    with SessionLocal() as db:
        session, case = intake_service.start_session(db, owner_id)
        return str(session.id), str(case.id)


def test_concurrent_start_returns_one_active_intake(owner_id):
    with ThreadPoolExecutor(max_workers=2) as pool:
        first, second = list(pool.map(lambda _: _start(owner_id), range(2)))
    assert first == second


def test_active_endpoint_returns_owned_resumable_session(owner_id):
    session_id, case_id = _start(owner_id)
    previous = app.dependency_overrides.get(authenticate)
    app.dependency_overrides[authenticate] = lambda: CurrentPrincipal(
        user_id=owner_id,
        subject=str(owner_id),
        roles=frozenset({"patient"}),
        auth_method="test",
    )
    try:
        response = TestClient(app).get(f"{BASE}/intake-sessions/active")
        assert response.status_code == 200
        assert response.json()["session_id"] == session_id
        assert response.json()["case_id"] == case_id
        assert response.json()["identity_complete"] is False
        assert response.json()["transcript"] == []
    finally:
        if previous is None:
            app.dependency_overrides.pop(authenticate, None)
        else:
            app.dependency_overrides[authenticate] = previous
