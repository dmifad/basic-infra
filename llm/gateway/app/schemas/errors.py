"""OpenAI-style error envelope (per ADR-0002).

Every error response the gateway emits is serialized as an ``ErrorEnvelope``.
The contract is defined in ``docs/api/openapi.yaml`` (schema ``ErrorEnvelope``).
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

ErrorType = Literal[
    "invalid_request_error",
    "authentication_error",
    "permission_error",
    "not_found_error",
    "rate_limit_error",
    "api_error",
    "backend_error",
]


class ErrorDetail(BaseModel):
    """The ``error`` object inside an error response."""

    message: str
    type: ErrorType
    code: str | None = None
    param: str | None = None


class ErrorEnvelope(BaseModel):
    """Top-level error response body: ``{"error": {...}}``."""

    error: ErrorDetail
