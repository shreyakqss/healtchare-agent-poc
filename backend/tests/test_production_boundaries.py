from types import SimpleNamespace

from fastapi.testclient import TestClient

import app.main as main_module
from tests.helpers import BASE


class _DatabaseProbe:
    def __init__(self, available: bool = True):
        self.available = available

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return None

    def execute(self, _):
        if not self.available:
            raise RuntimeError("database unavailable")


def test_responses_include_security_and_correlation_headers():
    client = TestClient(main_module.app)
    response = client.get("/health")
    api_response = client.get(f"{BASE}/auth/me")

    assert response.status_code == 200
    assert len(response.headers["x-request-id"]) == 32
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["cache-control"] == "no-store"
    assert api_response.headers["cache-control"] == "no-store"
    assert api_response.headers["pragma"] == "no-cache"


def test_readiness_reports_dependencies_without_error_details(monkeypatch):
    monkeypatch.setattr(main_module, "SessionLocal", lambda: _DatabaseProbe())
    monkeypatch.setattr(
        main_module,
        "get_hms",
        lambda: SimpleNamespace(status=lambda: SimpleNamespace(connected=True)),
    )

    response = TestClient(main_module.app).get("/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "checks": {"database": "ok", "hospital_system": "ok"},
    }


def test_readiness_returns_503_for_an_unavailable_dependency(monkeypatch):
    monkeypatch.setattr(main_module, "SessionLocal", lambda: _DatabaseProbe(available=False))
    monkeypatch.setattr(
        main_module,
        "get_hms",
        lambda: SimpleNamespace(status=lambda: SimpleNamespace(connected=True)),
    )

    response = TestClient(main_module.app).get("/ready")

    assert response.status_code == 503
    assert response.json()["checks"]["database"] == "unavailable"
    assert "detail" not in response.json()


def test_collection_limits_are_validated():
    client = TestClient(main_module.app)

    assert client.get(f"{BASE}/cases?limit=0").status_code == 422
    assert client.get(f"{BASE}/cases/my-visits?limit=101").status_code == 422
    assert client.get(f"{BASE}/hms/practitioners?limit=101").status_code == 422
    assert client.get(f"{BASE}/hms/appointment-requests?limit=0").status_code == 422
