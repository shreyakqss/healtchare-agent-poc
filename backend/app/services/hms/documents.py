"""Best-effort document push to the HMS with a single retry.

Used by the two places that forward artefacts to a linked record: uploaded attachments and
the finalised visit summary. Every other HMS call keeps single-attempt semantics.
"""

from __future__ import annotations

import logging
import time

from app.integrations.hms.base import HMSClient

logger = logging.getLogger(__name__)

RETRY_DELAY_SECONDS = 1.0
_ATTEMPTS = 2


def push_document_with_retry(
    hms: HMSClient, mrn: str, title: str, content: bytes, content_type: str = "text/plain"
) -> tuple[str | None, str | None]:
    """Returns `(hms_reference, error_type)`.

    `hms_reference` is None when the final attempt failed; `error_type` then carries the
    exception's class name (never its message - PHI-log-scrubbing convention) so the caller
    can write an audit event that surfaces the failure.
    """
    last_error: Exception | None = None
    for attempt in range(_ATTEMPTS):
        try:
            return hms.push_document(mrn, title, content, content_type), None
        except Exception as exc:  # noqa: BLE001 - best-effort push, never raises to the caller
            last_error = exc
            if attempt < _ATTEMPTS - 1:
                time.sleep(RETRY_DELAY_SECONDS)
    error_type = type(last_error).__name__ if last_error is not None else "UnknownError"
    logger.warning("Document write failed after retry (%s)", error_type)
    return None, error_type
