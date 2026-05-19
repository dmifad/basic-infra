"""Gateway exception hierarchy.

Every error the gateway raises deliberately is a ``GatewayError``. A single
exception handler (see ``main.py``) renders it as the OpenAI-style
``ErrorEnvelope`` with the correct HTTP status. This keeps error shaping in one
place and out of the route handlers.
"""
from __future__ import annotations

from .schemas.errors import ErrorType


class GatewayError(Exception):
    """Base for all deliberate gateway errors.

    Subclasses fix ``status_code`` and ``error_type``; instances may add a
    machine-readable ``code`` and the offending ``param``.
    """

    status_code: int = 500
    error_type: ErrorType = "api_error"

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        param: str | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.param = param


class InvalidRequestError(GatewayError):
    """Request was malformed or semantically invalid. -> 400."""

    status_code = 400
    error_type = "invalid_request_error"


class AuthenticationError(GatewayError):
    """Missing or invalid Bearer token. -> 401."""

    status_code = 401
    error_type = "authentication_error"


class ForbiddenError(GatewayError):
    """Authenticated, but not permitted (model access, tenant mismatch). -> 403."""

    status_code = 403
    error_type = "permission_error"


class ModelNotFoundError(GatewayError):
    """Requested model is not registered. -> 404."""

    status_code = 404
    error_type = "not_found_error"

    def __init__(self, message: str, *, param: str | None = "model") -> None:
        super().__init__(message, code="model_not_found", param=param)


class RateLimitError(GatewayError):
    """Per-tenant rate limit exceeded. -> 429, carries ``retry_after`` seconds."""

    status_code = 429
    error_type = "rate_limit_error"

    def __init__(self, message: str, *, retry_after: int) -> None:
        super().__init__(message, code="rate_limit_exceeded")
        self.retry_after = retry_after


class BackendUnavailableError(GatewayError):
    """Backend is unreachable or unhealthy. -> 503."""

    status_code = 503
    error_type = "backend_error"

    def __init__(self, message: str, *, code: str | None = "backend_unavailable") -> None:
        super().__init__(message, code=code)


class BackendTimeoutError(GatewayError):
    """Backend did not respond within the timeout. -> 504."""

    status_code = 504
    error_type = "backend_error"

    def __init__(self, message: str) -> None:
        super().__init__(message, code="backend_timeout")
