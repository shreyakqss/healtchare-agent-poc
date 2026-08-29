import uuid

from fastapi.testclient import TestClient

from app.core.config import settings
from app.db import SessionLocal
from app.main import app
from app.models import ApplicationUser
from app.security import CurrentPrincipal, authenticate
from tests.helpers import BASE


def _principal(user_id: uuid.UUID, *roles: str, clinic_id: str | None = None) -> CurrentPrincipal:
    return CurrentPrincipal(
        user_id=user_id,
        subject=str(user_id),
        roles=frozenset(roles),
        username="test.user",
        clinic_id=clinic_id,
        hms_username="careflow-test-clinician",
        auth_method="test",
    )


def _user(user_id: uuid.UUID) -> None:
    with SessionLocal() as db:
        if db.get(ApplicationUser, user_id) is None:
            db.add(
                ApplicationUser(
                    id=user_id,
                    issuer="https://issuer.test/realms/careflow",
                    subject=str(user_id),
                    username="test.user",
                    roles=["patient"],
                    active=True,
                )
            )
            db.commit()


def test_patient_case_ids_are_not_bearer_capabilities():
    owner_id, stranger_id = uuid.uuid4(), uuid.uuid4()
    _user(owner_id)
    _user(stranger_id)
    client = TestClient(app)
    app.dependency_overrides[authenticate] = lambda: _principal(owner_id, "patient")
    created = client.post(f"{BASE}/intake-sessions", json={})
    assert created.status_code == 201
    case_id = created.json()["case_id"]

    app.dependency_overrides[authenticate] = lambda: _principal(stranger_id, "patient")
    assert client.get(f"{BASE}/cases/{case_id}/patient-view").status_code == 404
    client.close()


def test_clinician_cannot_cross_clinic_and_admin_is_not_clinical():
    owner_id = uuid.uuid4()
    _user(owner_id)
    client = TestClient(app)
    app.dependency_overrides[authenticate] = lambda: _principal(owner_id, "patient")
    case_id = client.post(f"{BASE}/intake-sessions", json={}).json()["case_id"]

    app.dependency_overrides[authenticate] = lambda: _principal(uuid.uuid4(), "clinician", clinic_id="other-clinic")
    assert client.get(f"{BASE}/cases/{case_id}").status_code == 404

    app.dependency_overrides[authenticate] = lambda: _principal(
        uuid.uuid4(), "clinician", clinic_id=settings.DEFAULT_HOSPITAL_ID
    )
    assert client.get(f"{BASE}/cases/{case_id}").status_code == 200

    app.dependency_overrides[authenticate] = lambda: _principal(uuid.uuid4(), "admin")
    assert client.get(f"{BASE}/cases").status_code == 403
    client.close()


def test_missing_session_is_rejected():
    app.dependency_overrides.pop(authenticate, None)
    client = TestClient(app)
    assert client.get(f"{BASE}/auth/me").status_code == 401
    client.close()
