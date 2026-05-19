"""vams-llm-client — provider-agnostic LLM client (ADR-0004).

Usage::

    from vams_llm_client import LlmClient

    client = LlmClient.from_env()       # reads LLM_PROVIDER / LLM_BASE_URL / LLM_API_KEY
    resp = client.chat.completions.create(
        model="default-chat",
        messages=[{"role": "user", "content": "..."}],
    )
    emb = client.embeddings.create(model="default-embed", input=["text"])
    ranked = client.rerank(model="default-rerank", query="...", documents=[...])

Switching provider is a config change (``LLM_PROVIDER=openai``), never a code
change. ``client.capabilities()`` reports what the active provider supports.
"""
from __future__ import annotations

import os
from typing import Any

from .cache import EmbeddingCache
from .capabilities import KNOWN_PROVIDERS, PROVIDER_CAPABILITIES, resolve_model
from .errors import CapabilityNotAvailable, ProviderNotConfigured
from .models import ChatResponse, EmbeddingItem, EmbeddingResponse, RerankResponse
from .providers.base import Provider


class _Completions:
    """The ``client.chat.completions`` facade."""

    def __init__(self, client: LlmClient) -> None:
        self._client = client

    def create(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        response_format: dict[str, Any] | None = None,
        temperature: float = 0.1,
        max_tokens: int | None = None,
        **extra: Any,
    ) -> ChatResponse:
        """Create a chat completion."""
        return self._client._chat(
            model=model,
            messages=messages,
            response_format=response_format,
            temperature=temperature,
            max_tokens=max_tokens,
            **extra,
        )


class _Chat:
    """The ``client.chat`` namespace."""

    def __init__(self, client: LlmClient) -> None:
        self.completions = _Completions(client)


class _Embeddings:
    """The ``client.embeddings`` facade. Set ``cache_enabled`` to use the cache."""

    def __init__(self, client: LlmClient) -> None:
        self._client = client
        self.cache_enabled = False

    def create(self, *, model: str, input: str | list[str]) -> EmbeddingResponse:
        """Create embeddings for a string or list of strings."""
        return self._client._embed(
            model=model, text_input=input, use_cache=self.cache_enabled
        )


class LlmClient:
    """Provider-agnostic LLM client. Construct via :meth:`from_env`."""

    def __init__(
        self,
        *,
        provider: str,
        base_url: str | None = None,
        api_key: str | None = None,
        cache_dir: str | None = None,
    ) -> None:
        if provider not in KNOWN_PROVIDERS:
            raise ProviderNotConfigured(
                f"unknown provider {provider!r} (known: {', '.join(sorted(KNOWN_PROVIDERS))})"
            )
        self.provider = provider
        self.base_url = base_url
        self.api_key = api_key
        self.cache_dir = cache_dir
        self._provider_impl: Provider = _build_provider(provider, base_url, api_key)
        self._cache = EmbeddingCache(cache_dir) if cache_dir else None
        self.chat = _Chat(self)
        self.embeddings = _Embeddings(self)

    @classmethod
    def from_env(cls) -> LlmClient:
        """Build a client from ``LLM_PROVIDER`` / ``LLM_BASE_URL`` / ``LLM_API_KEY``.

        ``LLM_PROVIDER`` defaults to ``basic-infra``. Setting ``LLM_CACHE_DIR``
        makes the embedding cache available (still opt-in per call).
        """
        return cls(
            provider=os.getenv("LLM_PROVIDER", "basic-infra"),
            base_url=os.getenv("LLM_BASE_URL"),
            api_key=os.getenv("LLM_API_KEY"),
            cache_dir=os.getenv("LLM_CACHE_DIR"),
        )

    def capabilities(self) -> dict[str, bool]:
        """Return ``{"chat": bool, "embed": bool, "rerank": bool}`` for this provider."""
        caps = PROVIDER_CAPABILITIES[self.provider]
        return {"chat": "chat" in caps, "embed": "embed" in caps, "rerank": "rerank" in caps}

    def rerank(
        self,
        *,
        model: str,
        query: str,
        documents: list[str],
        top_n: int | None = None,
        return_documents: bool = True,
    ) -> RerankResponse:
        """Rerank ``documents`` against ``query`` (Cohere-style)."""
        self._require("rerank")
        return self._provider_impl.rerank(
            model=resolve_model(self.provider, model),
            query=query,
            documents=documents,
            top_n=top_n,
            return_documents=return_documents,
        )

    def close(self) -> None:
        """Release the provider's HTTP client and the embedding cache."""
        self._provider_impl.close()
        if self._cache is not None:
            self._cache.close()

    def _chat(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        response_format: dict[str, Any] | None,
        temperature: float,
        max_tokens: int | None,
        **extra: Any,
    ) -> ChatResponse:
        self._require("chat")
        return self._provider_impl.chat_completion(
            model=resolve_model(self.provider, model),
            messages=messages,
            response_format=response_format,
            temperature=temperature,
            max_tokens=max_tokens,
            **extra,
        )

    def _embed(
        self, *, model: str, text_input: str | list[str], use_cache: bool
    ) -> EmbeddingResponse:
        self._require("embed")
        resolved = resolve_model(self.provider, model)
        texts = [text_input] if isinstance(text_input, str) else list(text_input)

        cache = self._cache if use_cache else None
        if cache is None:
            return self._provider_impl.embeddings(model=resolved, inputs=texts)

        cached: dict[int, list[float]] = {}
        misses: list[str] = []
        for index, text in enumerate(texts):
            hit = cache.get(self.provider, resolved, text)
            if hit is None:
                misses.append(text)
            else:
                cached[index] = hit

        fetched: dict[str, list[float]] = {}
        if misses:
            fresh = self._provider_impl.embeddings(model=resolved, inputs=misses)
            for item in fresh.data:
                text = misses[item.index]
                fetched[text] = item.embedding
                cache.put(self.provider, resolved, text, item.embedding)

        items = [
            EmbeddingItem(
                index=index,
                embedding=cached[index] if index in cached else fetched[text],
            )
            for index, text in enumerate(texts)
        ]
        return EmbeddingResponse(model=resolved, data=items)

    def _require(self, capability: str) -> None:
        if not self.capabilities()[capability]:
            raise CapabilityNotAvailable(
                f"provider '{self.provider}' does not support '{capability}'"
            )


def _build_provider(
    provider: str, base_url: str | None, api_key: str | None
) -> Provider:
    """Instantiate the concrete provider (imported lazily to keep extras optional)."""
    if provider == "basic-infra":
        if not base_url or not api_key:
            raise ProviderNotConfigured(
                "basic-infra provider needs LLM_BASE_URL and LLM_API_KEY"
            )
        from .providers.basic_infra import BasicInfraProvider

        return BasicInfraProvider(base_url=base_url, api_key=api_key)
    if provider == "openai":
        if not api_key:
            raise ProviderNotConfigured("openai provider needs LLM_API_KEY")
        from .providers.openai import OpenAIProvider

        return OpenAIProvider(api_key=api_key, base_url=base_url)
    if provider == "anthropic":
        if not api_key:
            raise ProviderNotConfigured("anthropic provider needs LLM_API_KEY")
        from .providers.anthropic import AnthropicProvider

        return AnthropicProvider(api_key=api_key, base_url=base_url)
    raise ProviderNotConfigured(f"unknown provider {provider!r}")
