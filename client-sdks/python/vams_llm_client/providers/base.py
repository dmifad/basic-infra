"""Provider interface — the contract each provider implementation satisfies."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from ..models import ChatResponse, EmbeddingResponse, RerankResponse


class Provider(ABC):
    """A backend the SDK can dispatch to (basic-infra, OpenAI, Anthropic)."""

    name: str

    @abstractmethod
    def chat_completion(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        response_format: dict[str, Any] | None = None,
        temperature: float = 0.1,
        max_tokens: int | None = None,
        **extra: Any,
    ) -> ChatResponse:
        """Run a chat completion and return a normalized :class:`ChatResponse`."""

    @abstractmethod
    def embeddings(self, *, model: str, inputs: list[str]) -> EmbeddingResponse:
        """Embed ``inputs`` and return a normalized :class:`EmbeddingResponse`."""

    @abstractmethod
    def rerank(
        self,
        *,
        model: str,
        query: str,
        documents: list[str],
        top_n: int | None = None,
        return_documents: bool = True,
    ) -> RerankResponse:
        """Rerank ``documents`` against ``query``."""

    @abstractmethod
    def close(self) -> None:
        """Release any held resources (HTTP clients, etc.)."""
