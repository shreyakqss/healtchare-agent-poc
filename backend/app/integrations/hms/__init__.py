"""HMS adapter factory. Everything above this package reaches the hospital system only
through `get_hms()` and the `HMSClient` protocol - swapping providers touches nothing else.

Settings and adapters are imported inside the factory so this package can be imported by
`app.core.config` (for the OpenEMR scope defaults) without a cycle.
"""

from functools import lru_cache

from app.integrations.hms.base import HMSClient

_override: HMSClient | None = None


@lru_cache(maxsize=1)
def _build_hms() -> HMSClient:
    from app.core.config import settings

    if settings.HMS_PROVIDER == "openemr":
        from app.integrations.hms.openemr import FhirHMS

        return FhirHMS(
            base_url=settings.OPENEMR_BASE_URL,
            fhir_path=settings.OPENEMR_FHIR_PATH,
            api_path=settings.OPENEMR_API_PATH,
            token_url=settings.OPENEMR_TOKEN_URL,
            client_id=settings.OPENEMR_CLIENT_ID,
            client_secret=settings.OPENEMR_CLIENT_SECRET,
            scopes=settings.OPENEMR_SCOPES,
            username=settings.OPENEMR_USERNAME,
            password=settings.OPENEMR_PASSWORD,
        )
    raise RuntimeError(f"Unsupported HMS provider {settings.HMS_PROVIDER!r}")


def get_hms() -> HMSClient:
    return _override if _override is not None else _build_hms()


def use_hms(client: HMSClient | None) -> None:
    """Install a stand-in hospital system for the whole process.

    The one seam the test suite uses (`tests/conftest.py`) so it can exercise the real API,
    services and workflows without a live OpenEMR. Never called by application code.
    """
    global _override
    _override = client


__all__ = ["HMSClient", "get_hms", "use_hms"]
