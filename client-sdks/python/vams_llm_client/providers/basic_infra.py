"""basic-infra provider — a thin HTTP client for the platform gateway.

Speaks the platform's OpenAI-compatible + Cohere-style-rerank contract
(ADR-0002) over plain HTTP with a Bearer token.
"""
from __future__ import annotations

from typing import Any

import httpx

from ..errors import PlatformError
from ..models import (
    ChatResponse,
    EmbeddingItem,
    EmbeddingResponse,
    RerankItem,
    RerankResponse,
)
from .base import Provider

_DEFAULT_TIMEOUT = 900.0


class BasicInfraProvider(Provider):
    """Provider that talks to a locally-hosted basic-infra gateway."""

    name = "basic-infra"

    def __init__(
        self, *, base_url: str, api_key: str, timeout: float = _DEFAULT_TIMEOUT
    ) -> None:
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
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
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
        }
        if response_format is not None:
            payload["response_format"] = response_format
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        payload.update(extra)
        return ChatResponse.model_validate(self._post("/chat/completions", payload))

    def embeddings(self, *, model: str, inputs: list[str]) -> EmbeddingResponse:
        data = self._post("/embeddings", {"model": model, "input": inputs})
        items = [
            EmbeddingItem(index=int(d["index"]), embedding=list(d["embedding"]))
            for d in data["data"]
        ]
        return EmbeddingResponse(model=data.get("model", model), data=items)

    def rerank(
        self,
        *,
        model: str,
        query: str,
        documents: list[str],
        top_n: int | None = None,
        return_documents: bool = True,
    ) -> RerankResponse:
        payload: dict[str, Any] = {
            "model": model,
            "query": query,
            "documents": documents,
            "return_documents": return_documents,
        }
        if top_n is not None:
            payload["top_n"] = top_n
        data = self._post("/rerank", payload)
        results = [
            RerankItem(
                index=int(r["index"]),
                relevance_score=float(r["relevance_score"]),
                document=(r.get("document") or {}).get("text"),
            )
            for r in data["results"]
        ]
        return RerankResponse(model=data.get("model", model), results=results)

    def close(self) -> None:
        self._client.close()

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            resp = self._client.post(path, json=payload)
        except httpx.HTTPError as exc:
            raise PlatformError(f"basic-infra platform unreachable: {exc}") from exc
        if resp.status_code >= 400:
            raise PlatformError(
                f"basic-infra returned HTTP {resp.status_code}: {_error_message(resp)}",
                status_code=resp.status_code,
            )
        body: dict[str, Any] = resp.json()
        return body


def _error_message(resp: httpx.Response) -> str:
    """Pull the message out of an OpenAI-style error envelope, if present."""
    try:
        return str(resp.json()["error"]["message"])
    except (ValueError, KeyError, TypeError):
        return resp.text[:200]
