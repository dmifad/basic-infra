"""Anthropic provider — wraps the ``anthropic`` package (optional extra).

Anthropic has no native embeddings or rerank — those raise
:class:`CapabilityNotAvailable`. Structured output (``response_format`` of type
``json_schema``) is translated to Anthropic's tool_use pattern: one tool whose
``input_schema`` is the requested schema, forced via ``tool_choice``; the
tool-call input is returned as the message content.
"""
from __future__ import annotations

import json
from typing import Any

from ..errors import CapabilityNotAvailable, ProviderDependencyMissing
from ..models import (
    ChatChoice,
    ChatMessage,
    ChatResponse,
    EmbeddingResponse,
    RerankResponse,
)
from .base import Provider

_DEFAULT_MAX_TOKENS = 1024


class AnthropicProvider(Provider):
    """Provider that talks to Anthropic's cloud API."""

    name = "anthropic"

    def __init__(self, *, api_key: str, base_url: str | None = None) -> None:
        try:
            from anthropic import Anthropic
        except ImportError as exc:  # pragma: no cover - exercised only without the extra
            raise ProviderDependencyMissing(
                "LLM_PROVIDER=anthropic needs the 'anthropic' extra "
                "(install vams-llm-client[anthropic])"
            ) from exc
        self._client = (
            Anthropic(api_key=api_key, base_url=base_url)
            if base_url
            else Anthropic(api_key=api_key)
        )

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
        system, conversation = _split_system(messages)
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": conversation,
            "max_tokens": max_tokens or _DEFAULT_MAX_TOKENS,
            "temperature": temperature,
        }
        if system:
            kwargs["system"] = system

        tool_name: str | None = None
        if response_format is not None and response_format.get("type") == "json_schema":
            schema = response_format["json_schema"]
            tool_name = schema.get("name", "structured_output")
            kwargs["tools"] = [
                {
                    "name": tool_name,
                    "description": "Return the result strictly in this JSON schema.",
                    "input_schema": schema["schema"],
                }
            ]
            kwargs["tool_choice"] = {"type": "tool", "name": tool_name}
        kwargs.update(extra)

        resp = self._client.messages.create(**kwargs)
        return ChatResponse(
            id=getattr(resp, "id", ""),
            model=getattr(resp, "model", model),
            choices=[
                ChatChoice(
                    index=0,
                    message=ChatMessage(
                        role="assistant", content=_extract_content(resp, tool_name)
                    ),
                    finish_reason=getattr(resp, "stop_reason", None),
                )
            ],
        )

    def embeddings(self, *, model: str, inputs: list[str]) -> EmbeddingResponse:
        raise CapabilityNotAvailable("Anthropic has no embeddings endpoint")

    def rerank(
        self,
        *,
        model: str,
        query: str,
        documents: list[str],
        top_n: int | None = None,
        return_documents: bool = True,
    ) -> RerankResponse:
        raise CapabilityNotAvailable("Anthropic has no rerank endpoint")

    def close(self) -> None:
        self._client.close()


def _split_system(messages: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    """Split OpenAI-style messages into Anthropic's (system, conversation)."""
    system_parts: list[str] = []
    conversation: list[dict[str, Any]] = []
    for message in messages:
        if message.get("role") == "system":
            system_parts.append(str(message.get("content", "")))
        else:
            conversation.append(
                {"role": message["role"], "content": message["content"]}
            )
    return "\n\n".join(system_parts), conversation


def _extract_content(response: Any, tool_name: str | None) -> str:
    """Pull text (or forced tool-call JSON) out of an Anthropic message."""
    for block in getattr(response, "content", []):
        if getattr(block, "type", None) == "tool_use" and (
            tool_name is None or getattr(block, "name", None) == tool_name
        ):
            return json.dumps(getattr(block, "input", {}))
    texts = [
        getattr(block, "text", "")
        for block in getattr(response, "content", [])
        if getattr(block, "type", None) == "text"
    ]
    return "".join(texts)
