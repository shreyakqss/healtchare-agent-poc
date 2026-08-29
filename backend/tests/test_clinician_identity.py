"""verify_clinician: the one place a failed HMS login becomes a 401."""

import asyncio

import pytest

from app.core.errors import Unauthorized
from app.integrations.hms.schemas import VerifiedIdentity
from app.services import clinician_identity


class _HMS:
    def __init__(self, identity):
        self._identity = identity

    def verify_credentials(self, username, password):
        return self._identity


def test_returns_identity_when_hms_accepts(monkeypatch):
    monkeypatch.setattr(clinician_identity, "get_hms", lambda: _HMS(VerifiedIdentity(id="p1", name="Dr. A")))
    assert clinician_identity.verify_clinician("dr_a", "pw").id == "p1"


def test_raises_unauthorized_when_hms_rejects(monkeypatch):
    monkeypatch.setattr(clinician_identity, "get_hms", lambda: _HMS(None))
    with pytest.raises(Unauthorized):
        clinician_identity.verify_clinician("dr_a", "wrong")


def test_async_variant_offloads_and_preserves_error(monkeypatch):
    monkeypatch.setattr(clinician_identity, "get_hms", lambda: _HMS(None))
    with pytest.raises(Unauthorized):
        asyncio.run(clinician_identity.verify_clinician_async("dr_a", "wrong"))
