"""OpenAI provider — wraps the official ``openai`` package (optional extra).

OpenAI has no rerank endpoint; ``rerank`` raises :class:`CapabilityNotAvailable`.
"""
from __future__ import annotations

from typing import Any

from ..errors import CapabilityNotAvailable, ProviderDependencyMissing
from ..models import (
    ChatChoice,
    ChatMessage,
    ChatResponse,
    EmbeddingItem,
    EmbeddingResponse,
    RerankResponse,
)
from .base import Provider


class OpenAIProvider(Provider):
    """Provider that talks to OpenAI's cloud API."""

    name = "openai"

    def __init__(self, *, api_key: str, base_url: str | None = None) -> None:
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover - exercised only without the extra
            raise ProviderDependencyMissing(
                "LLM_PROVIDER=openai needs the 'openai' extra "
                "(install vams-llm-client[openai])"
            ) from exc
        self._client = OpenAI(api_key=api_key, base_url=base_url)

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
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
        }
        if response_format is not None:
            kwargs["response_format"] = response_format
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        kwargs.update(extra)
        resp = self._client.chat.completions.create(**kwargs)
        choices = [
            ChatChoice(
                index=choice.index,
                message=ChatMessage(
                    role=choice.message.role, content=choice.message.content or ""
                ),
                finish_reason=choice.finish_reason,
            )
            for choice in resp.choices
        ]
        return ChatResponse(id=resp.id or "", model=resp.model, choices=choices)

    def embeddings(self, *, model: str, inputs: list[str]) -> EmbeddingResponse:
        resp = self._client.embeddings.create(model=model, input=inputs)
        items = [
            EmbeddingItem(index=item.index, embedding=list(item.embedding))
            for item in resp.data
        ]
        return EmbeddingResponse(model=resp.model, data=items)

    def rerank(
        self,
        *,
        model: str,
        query: str,
        documents: list[str],
        top_n: int | None = None,
        return_documents: bool = True,
    ) -> RerankResponse:
        raise CapabilityNotAvailable("OpenAI has no rerank endpoint")

    def close(self) -> None:
        self._client.close()
