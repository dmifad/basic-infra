"""vams-llm-client error hierarchy."""
from __future__ import annotations


class VamsLlmError(Exception):
    """Base for all SDK errors."""


class ProviderNotConfigured(VamsLlmError):
    """``LLM_PROVIDER`` is unset or names an unknown provider."""


class CapabilityNotAvailable(VamsLlmError):
    """The active provider does not support the requested capability.

    e.g. calling ``client.rerank()`` while configured against Anthropic.
    """


class ModelNotAvailable(VamsLlmError):
    """The requested model is not available for the active provider."""


class ProviderDependencyMissing(VamsLlmError):
    """The provider needs an optional package that is not installed.

    e.g. ``LLM_PROVIDER=openai`` without the ``openai`` extra installed.
    """


class PlatformError(VamsLlmError):
    """The platform (or cloud provider) returned an error response."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
