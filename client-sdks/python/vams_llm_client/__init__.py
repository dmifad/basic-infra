"""vams-llm-client — provider-agnostic LLM client SDK for the basic-infra platform."""
from __future__ import annotations

from .client import LlmClient
from .errors import (
    CapabilityNotAvailable,
    ModelNotAvailable,
    PlatformError,
    ProviderDependencyMissing,
    ProviderNotConfigured,
    VamsLlmError,
)
from .models import ChatResponse, EmbeddingResponse, RerankResponse

__version__ = "0.1.0"

__all__ = [
    "LlmClient",
    "ChatResponse",
    "EmbeddingResponse",
    "RerankResponse",
    "VamsLlmError",
    "ProviderNotConfigured",
    "CapabilityNotAvailable",
    "ModelNotAvailable",
    "ProviderDependencyMissing",
    "PlatformError",
    "__version__",
]
