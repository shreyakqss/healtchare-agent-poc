"""Per-action clinician identity check against the HMS's own login.

Not a session or auth system: every review, consultation note and finalisation carries the
clinician's HMS username/password and is attributed to the identity the HMS returns. A
failed check is a 401 regardless of which endpoint asked.
"""

from __future__ import annotations

import asyncio

from app.core.errors import Unauthorized
from app.integrations.hms import get_hms
from app.integrations.hms.schemas import VerifiedIdentity

INVALID_CREDENTIALS = "Invalid clinician credentials."


def verify_clinician(username: str, password: str) -> VerifiedIdentity:
    identity = get_hms().verify_credentials(username, password)
    if identity is None:
        raise Unauthorized(INVALID_CREDENTIALS)
    return identity


async def verify_clinician_async(username: str, password: str) -> VerifiedIdentity:
    """For async endpoints: the check is a blocking OAuth round-trip (plus a JWKS fetch on a
    cache miss) and must not stall the event loop."""
    return await asyncio.to_thread(verify_clinician, username, password)
