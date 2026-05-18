"""vams-llm-client — provider-agnostic LLM client.

Usage:
    from vams_llm_client import LlmClient

    client = LlmClient.from_env()       # picks up LLM_PROVIDER from env
    resp = client.chat.completions.create(
        model="t-pro-it-2.1-q8",        # or "default-chat" alias
        messages=[{"role": "user", "content": "..."}],
    )

See:
    docs/adr/0004-provider-switching.md
"""
from __future__ import annotations

import os
from typing import Any


# ─── Provider registry ─────────────────────────────────────────────────────

PROVIDER_MODEL_ALIASES: dict[str, dict[str, str]] = {
    "basic-infra": {
        "default-chat":   "t-pro-it-2.1-q8",
        "default-embed":  "bge-m3",
        "default-rerank": "bge-reranker-v2-m3",
    },
    "openai": {
        "default-chat":  "gpt-4o-mini",
        "default-embed": "text-embedding-3-small",
        # no native rerank
    },
    "anthropic": {
        "default-chat": "claude-haiku-4-5",
        # no native embed/rerank
    },
}

# Static capabilities per provider — checked at client construction
PROVIDER_CAPABILITIES: dict[str, frozenset[str]] = {
    "basic-infra": frozenset({"chat", "embed", "rerank", "structured"}),
    "openai":      frozenset({"chat", "embed", "structured"}),
    "anthropic":   frozenset({"chat", "structured"}),
}


# ─── Client ────────────────────────────────────────────────────────────────

class LlmClient:
    """Provider-agnostic client.

    The actual provider implementation lives in providers/*.py and is selected
    at construction time. Subsequent calls dispatch through the provider.
    """

    def __init__(
        self,
        *,
        provider: str,
        base_url: str | None = None,
        api_key: str | None = None,
        cache_dir: str | None = None,
    ) -> None:
        self.provider = provider
        self.base_url = base_url
        self.api_key = api_key
        self.cache_dir = cache_dir

        # TODO(week4-phase-6):
        # - validate provider in PROVIDER_CAPABILITIES
        # - instantiate the actual provider:
        #     from .providers.basic_infra import BasicInfraProvider
        #     from .providers.openai import OpenAIProvider
        #     from .providers.anthropic import AnthropicProvider
        # - expose .chat, .embeddings, .rerank facades
        raise NotImplementedError("week4-phase-6")

    @classmethod
    def from_env(cls) -> LlmClient:
        """Read LLM_PROVIDER, LLM_BASE_URL, LLM_API_KEY, LLM_CACHE_DIR from env."""
        provider = os.getenv("LLM_PROVIDER", "basic-infra")
        return cls(
            provider=provider,
            base_url=os.getenv("LLM_BASE_URL"),
            api_key=os.getenv("LLM_API_KEY"),
            cache_dir=os.getenv("LLM_CACHE_DIR"),
        )

    def capabilities(self) -> frozenset[str]:
        return PROVIDER_CAPABILITIES[self.provider]

    def resolve_model(self, alias_or_id: str) -> str:
        """Resolve semantic aliases like 'default-chat' to provider's actual model."""
        aliases = PROVIDER_MODEL_ALIASES.get(self.provider, {})
        return aliases.get(alias_or_id, alias_or_id)


# ─── Errors ────────────────────────────────────────────────────────────────

class VamsLlmError(Exception):
    """Base for all SDK errors."""


class ProviderNotConfigured(VamsLlmError):
    """LLM_PROVIDER not set or unknown."""


class CapabilityNotAvailable(VamsLlmError):
    """Requested capability not supported by current provider.

    e.g., calling client.rerank() with provider=anthropic.
    """


class ModelNotAvailable(VamsLlmError):
    """Requested model not registered with current provider."""
