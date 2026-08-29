from __future__ import annotations

import base64
import uuid
from dataclasses import dataclass
from datetime import datetime

from app.core.errors import Unprocessable
from app.models import PatientCase


@dataclass(frozen=True)
class CasePage:
    items: list[PatientCase]
    next_cursor: str | None


def encode_case_cursor(case: PatientCase) -> str:
    raw = f"{case.created_at.isoformat()}|{case.id}".encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_case_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode()
        created_at, case_id = raw.rsplit("|", 1)
        parsed = datetime.fromisoformat(created_at)
        if parsed.tzinfo is None:
            raise ValueError
        return parsed, uuid.UUID(case_id)
    except (UnicodeDecodeError, ValueError) as exc:
        raise Unprocessable("Invalid pagination cursor.") from exc
