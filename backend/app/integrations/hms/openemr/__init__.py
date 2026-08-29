"""OpenEMR FHIR adapter.

`FhirHMS` implements `HMSClient` against a real OpenEMR instance:

- `auth.py`   OAuth2 token lifecycle (password or client-credentials grant) and OIDC
              id_token verification against OpenEMR's JWKS.
- `fhir.py`   Pure FHIR resource <-> flat HMS schema mapping. No I/O.
- `client.py` The adapter itself: HTTP calls, resource orchestration, write-side guards.
"""

from app.integrations.hms.openemr.client import FhirHMS

__all__ = ["FhirHMS"]
