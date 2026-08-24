from functools import lru_cache

from app.core.config import settings
from app.integrations.hms.base import HMSClient
from app.integrations.hms.mock import MockHMS


@lru_cache(maxsize=1)
def get_hms() -> HMSClient:
    if settings.HMS_PROVIDER == "mock":
        return MockHMS(settings.HMS_FIXTURE)
    raise RuntimeError(f"Unsupported HMS provider {settings.HMS_PROVIDER!r}")


__all__ = ["HMSClient", "get_hms"]