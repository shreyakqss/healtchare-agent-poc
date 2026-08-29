import json
import logging
import re
from contextvars import ContextVar, Token
from datetime import UTC, datetime

_PHONE_RE = re.compile(r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b")
_MRN_RE = re.compile(r"\bMRN-\d+\b", re.IGNORECASE)
_request_id: ContextVar[str] = ContextVar("request_id", default="-")


def _redact(value: str) -> str:
    return _MRN_RE.sub("[MRN-REDACTED]", _PHONE_RE.sub("[PHONE-REDACTED]", value))


def bind_request_id(value: str) -> Token[str]:
    return _request_id.set(value)


def reset_request_id(token: Token[str]) -> None:
    _request_id.reset(token)


class RequestContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:
            message = "Log message could not be formatted."
        record.msg = _redact(message)
        record.args = ()
        record.request_id = _request_id.get()
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "request_id": getattr(record, "request_id", "-"),
            "message": record.getMessage(),
        }
        for name in ("http_method", "http_route", "status_code", "duration_ms"):
            value = getattr(record, name, None)
            if value is not None:
                payload[name] = value
        if record.exc_info:
            payload["exception_type"] = record.exc_info[0].__name__
        return json.dumps(payload, separators=(",", ":"), ensure_ascii=False)


def configure_logging(debug: bool, structured: bool = False) -> None:
    handler = logging.StreamHandler()
    formatter: logging.Formatter = (
        JsonFormatter()
        if structured
        else logging.Formatter("%(asctime)s %(levelname)s %(name)s [%(request_id)s]: %(message)s")
    )
    handler.setFormatter(formatter)
    handler.addFilter(RequestContextFilter())
    logging.basicConfig(level=logging.DEBUG if debug else logging.INFO, handlers=[handler], force=True)
    for logger_name in ("httpcore", "httpcore2", "httpx", "httpx2", "openai"):
        logging.getLogger(logger_name).setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").disabled = True
