from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.schemas.requests import IdentityFormRequest


def _identity(**overrides):
    values = {
        "name": "Test Patient",
        "birth_date": "1990-01-01",
        "gender": "female",
        "address_line1": "1 Test Street",
        "city": "Pune",
        "state": "MH",
        "postal_code": "411001",
        "country": "India",
        "contact_preference": "email",
        "email": "patient@example.test",
    }
    return IdentityFormRequest(**(values | overrides))


def test_birth_date_cannot_be_in_the_future():
    future = (datetime.now(UTC).date() + timedelta(days=1)).isoformat()
    with pytest.raises(ValidationError, match="cannot be in the future"):
        _identity(birth_date=future)


def test_current_birth_date_is_accepted():
    assert _identity(birth_date=datetime.now(UTC).date().isoformat()).birth_date == datetime.now(UTC).date()
