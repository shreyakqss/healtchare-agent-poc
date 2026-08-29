"""The clinic's own identity, taken from the hospital system.

The clinic YAML defines policy (departments, routing keywords, triage rules). *Who the
clinic is* - name, address, phone - already lives in the hospital system's facility record,
so it is read from there rather than kept as a second copy that can drift. The YAML
`hospital:` block is the fallback for when the hospital system is unreachable or has no
facility on file.
"""

from __future__ import annotations

import logging
from typing import Any

from app.integrations.hms import get_hms
from app.services import hospital_config

logger = logging.getLogger(__name__)


def effective_hospital() -> dict[str, Any]:
    """The `hospital` block to show: the hospital system's facility, overlaid on the YAML.

    Carries `source: "hms" | "config"` so the UI can say where the details came from.
    """
    configured = dict(hospital_config.hospital())
    try:
        facility = get_hms().get_facility()
    except Exception as exc:  # noqa: BLE001 - the clinic name must never break a page
        logger.debug("Facility lookup failed, using the configured clinic details (%s)", type(exc).__name__)
        facility = None
    if facility is None:
        return {**configured, "source": "config"}

    address = facility.address
    return {
        **configured,
        "name": facility.name,
        "phone": facility.phone,
        "email": facility.email,
        "website": facility.website,
        "address": address.model_dump() if address else None,
        "source": "hms",
    }
