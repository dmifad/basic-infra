"""Abstract backend adapter interface.

Per ADR-0005: every backend kind (openai_compat, tei, anthropic, ...) implements
this contract. The router invokes the adapter; the adapter translates
platform-shape calls into backend-specific calls.

Concrete implementations live next to this file:
    openai_compat.py    — llama.cpp server, vLLM, generic OpenAI-compatible
    tei.py              — TEI embeddings
    tei_rerank.py       — TEI rerank
    anthropic.py        — Anthropic native API (with translation)
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from ..schemas.chat import ChatCompletionRequest, ChatCompletionResponse
from ..schemas.embeddings import EmbeddingRequest, EmbeddingResponse
from ..schemas.rerank import RerankRequest, RerankResponse


@dataclass(frozen=True)
class BackendModel:
    """A model entry within a backend, as declared in backends.yaml."""
    id: str                          # platform-facing model ID, e.g. "t-pro-it-2.1-q8"
    backend_model_name: str          # backend's native name, e.g. "T-pro-it-2.1-Q8_0.gguf"
    capabilities: frozenset[str]     # subset of {chat, completions, embeddings, rerank, structured}


class BackendAdapter(ABC):
    """Abstract base for all backend adapters."""

    def __init__(
        self,
        *,
        name: str,
        base_url: str,
        timeout_seconds: int = 900,
        api_key: str | None = None,
    ) -> None:
        self.name = name
        self.base_url = base_url
        self.timeout_seconds = timeout_seconds
        self.api_key = api_key

    @abstractmethod
    async def chat_completion(
        self,
        request: ChatCompletionRequest,
        model: BackendModel,
    ) -> ChatCompletionResponse:
        """Translate and forward a chat completion request to the backend.

        Implementations:
            - Map request.model from platform ID to model.backend_model_name
            - Translate response_format per backend's guided-decoding capability
            - Stream → consume to non-stream (streaming not supported in v1)
            - Return ChatCompletionResponse with GatewayMetadata.backend = self.name
        """

    @abstractmethod
    async def embedding(
        self,
        request: EmbeddingRequest,
        model: BackendModel,
    ) -> EmbeddingResponse:
        """Translate and forward an embedding request to the backend."""

    @abstractmethod
    async def rerank(
        self,
        request: RerankRequest,
        model: BackendModel,
    ) -> RerankResponse:
        """Translate and forward a rerank request to the backend."""

    @abstractmethod
    async def health(self) -> bool:
        """Cheap probe — used by HealthChecker background task."""

    def supports(self, capability: str) -> bool:
        """Static capability of this adapter kind.

        Override in subclasses if dynamic capabilities are needed.
        """
        raise NotImplementedError("week4-phase-4: implement in subclass")


class AdapterError(Exception):
    """Base for adapter errors that surface as HTTP errors via exception handlers."""


class BackendUnavailable(AdapterError):
    """Backend is unreachable or unhealthy. Translates to 503."""


class CapabilityNotSupported(AdapterError):
    """Backend received a request for a capability it doesn't support. Translates to 400."""


class TranslationFailure(AdapterError):
    """Couldn't translate platform request to backend format. Translates to 500 with log."""
