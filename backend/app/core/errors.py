"""Domain errors mapped to HTTP responses in app/main.py."""


class DomainError(Exception):
    status_code = 400

    def __init__(self, detail: str):
        super().__init__(detail)
        self.detail = detail


class NotFound(DomainError):
    status_code = 404


class Conflict(DomainError):
    status_code = 409


class Forbidden(DomainError):
    status_code = 403


class Unauthorized(DomainError):
    status_code = 401


class ServiceUnavailable(DomainError):
    status_code = 503


class InvalidConfig(DomainError):
    status_code = 422


class HMSRejected(DomainError):
    """The hospital system refused a write as invalid (e.g. a required demographic missing
    or malformed). The caller's data is at fault, so this is a 422 rather than a 502 - and a
    readable message, never an unhandled 500 carrying a raw upstream error."""

    status_code = 422


class Unprocessable(DomainError):
    """A request was well-formed but the domain rejects it - e.g. an intake form
    submitted with required fields still missing after form + extraction processing."""

    status_code = 422


class RateLimited(DomainError):
    status_code = 429

    def __init__(self, retry_after: int):
        super().__init__("Too many requests. Try again later.")
        self.retry_after = retry_after
