"""Pure demographic helpers shared by intake and the hospital-system adapter."""

from __future__ import annotations

from datetime import date


def age_from_birth_date(birth_date: date, today: date | None = None) -> int:
    """Whole years between `birth_date` and `today` (defaults to the current date)."""
    today = today or date.today()
    had_birthday = (today.month, today.day) >= (birth_date.month, birth_date.day)
    return today.year - birth_date.year - (0 if had_birthday else 1)


def parse_fhir_date(value: str | None) -> date | None:
    """`YYYY-MM-DD[THH:MM...]` -> date, or None when absent or unparseable."""
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None
