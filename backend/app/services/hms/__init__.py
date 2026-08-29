"""Application-side HMS behaviour that sits above the adapter protocol.

The adapter (`app.integrations.hms`) knows how to talk to a hospital system. These modules
decide *what* CareFlow sends it and how failures degrade:

- `clinic`        the clinic's own identity, read from the hospital system's facility
- `documents`     best-effort document push with one retry
- `audit_forward` mirror of high-value audit events onto the linked HMS record
- `intake_sync`   the clinician-approved intake payload written at finalisation
- `roster`        live practitioners overlaid on the YAML doctor roster
"""

from app.services.hms.audit_forward import forward_audit_note
from app.services.hms.clinic import effective_hospital
from app.services.hms.documents import push_document_with_retry
from app.services.hms.intake_sync import reviewed_payload
from app.services.hms.roster import effective_doctors_config, effective_roster

__all__ = [
    "effective_doctors_config",
    "effective_hospital",
    "effective_roster",
    "forward_audit_note",
    "push_document_with_retry",
    "reviewed_payload",
]
