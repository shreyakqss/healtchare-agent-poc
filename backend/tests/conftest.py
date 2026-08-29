"""Test wiring.

There is no fake hospital system: the integration tests talk to the OpenEMR configured in
`backend/.env`, registering real patients and writing real chart rows, because that is the
only way to know the integration works. Point them at a test instance only.

Unit tests (`-m "not integration"`) never touch it. When OpenEMR is unreachable the
integration tests are skipped with the reason, never silently passed.
"""

import os
import sys
import uuid
from pathlib import Path

import pytest
from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("AUTH_SESSION_SECRET", "careflow-test-session-secret-at-least-32-characters")
os.environ.setdefault("RATE_LIMITING_ENABLED", "False")

_UNAVAILABLE: str | None = None
_TEST_ISSUER = "https://issuer.test/realms/careflow"
_TEST_SUBJECT_PREFIX = f"test-user-{uuid.uuid4().hex}"


@pytest.fixture(autouse=True)
def authenticated_requests():
    from app.core.config import settings
    from app.db import SessionLocal, engine
    from app.main import app
    from app.models import ApplicationUser, AuthSession, CaseOwner
    from app.security import CurrentPrincipal, authenticate

    for table in (ApplicationUser.__table__, AuthSession.__table__, CaseOwner.__table__):
        table.create(engine, checkfirst=True)
    test_user_id = uuid.uuid4()
    hms_username = settings.OPENEMR_USERNAME or "careflow-test-clinician"
    db = SessionLocal()
    try:
        user = ApplicationUser(
            id=test_user_id,
            issuer=_TEST_ISSUER,
            subject=f"{_TEST_SUBJECT_PREFIX}-{test_user_id}",
        )
        db.add(user)
        user.username = "careflow.test"
        user.hms_username = hms_username
        user.roles = ["admin", "clinician", "patient"]
        user.clinic_id = settings.DEFAULT_HOSPITAL_ID
        user.active = True
        db.commit()
    finally:
        db.close()

    principal = CurrentPrincipal(
        user_id=test_user_id,
        subject=f"{_TEST_SUBJECT_PREFIX}-{test_user_id}",
        roles=frozenset({"admin", "clinician", "patient"}),
        username="careflow.test",
        clinic_id=settings.DEFAULT_HOSPITAL_ID,
        hms_username=hms_username,
        auth_method="test",
    )
    app.dependency_overrides[authenticate] = lambda: principal
    try:
        yield
    finally:
        app.dependency_overrides.pop(authenticate, None)


@pytest.fixture(scope="session", autouse=True)
def cleanup_synthetic_application_users():
    yield

    from app.db import SessionLocal
    from app.models import ApplicationUser, CaseOwner, IntakeSession, PatientCase

    db = SessionLocal()
    try:
        user_ids = select(ApplicationUser.id).where(
            ApplicationUser.issuer == _TEST_ISSUER,
            ApplicationUser.subject.like(f"{_TEST_SUBJECT_PREFIX}-%"),
        )
        case_ids = select(CaseOwner.case_id).where(CaseOwner.user_id.in_(user_ids))
        session_ids = select(PatientCase.session_id).where(PatientCase.id.in_(case_ids))
        db.query(IntakeSession).filter(IntakeSession.id.in_(session_ids)).delete(synchronize_session=False)
        db.query(ApplicationUser).filter(ApplicationUser.id.in_(user_ids)).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()


def _hospital_system_unavailable() -> str | None:
    """None when the configured hospital system answered; otherwise why it did not."""
    global _UNAVAILABLE
    if _UNAVAILABLE is not None:
        return _UNAVAILABLE or None
    from app.core.config import settings
    from app.integrations.hms import get_hms

    if not (settings.OPENEMR_CLIENT_ID and settings.OPENEMR_USERNAME):
        _UNAVAILABLE = "OPENEMR_CLIENT_ID / OPENEMR_USERNAME are not set in backend/.env"
    else:
        try:
            _UNAVAILABLE = "" if get_hms().status().connected else f"{settings.OPENEMR_BASE_URL} did not answer"
        except Exception as exc:  # noqa: BLE001 - any failure means "not available"
            _UNAVAILABLE = f"{type(exc).__name__} talking to {settings.OPENEMR_BASE_URL}"
    return _UNAVAILABLE or None


def pytest_collection_modifyitems(config, items):
    integration = [item for item in items if item.get_closest_marker("integration")]
    if not integration:
        return
    reason = _hospital_system_unavailable()
    if reason is None:
        return
    skip = pytest.mark.skip(reason=f"needs a reachable OpenEMR ({reason}) - see README.md's OpenEMR setup section")
    for item in integration:
        item.add_marker(skip)


@pytest.fixture
def hms():
    """The live hospital system, for tests that need to seed or inspect it."""
    from app.integrations.hms import get_hms

    return get_hms()
