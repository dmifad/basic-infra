"""Per-provider capability and model-alias tables (ADR-0004)."""
from __future__ import annotations

# What each provider can do. Checked at client construction and per call.
PROVIDER_CAPABILITIES: dict[str, frozenset[str]] = {
    "basic-infra": frozenset({"chat", "embed", "rerank", "structured"}),
    "openai": frozenset({"chat", "embed", "structured"}),
    "anthropic": frozenset({"chat", "structured"}),
}

# Semantic model aliases — decouple project code from concrete model ids.
PROVIDER_MODEL_ALIASES: dict[str, dict[str, str]] = {
    "basic-infra": {
        "default-chat": "t-pro-it-2.1-q8",
        "default-embed": "bge-m3",
        "default-rerank": "bge-reranker-v2-m3",
    },
    "openai": {
        "default-chat": "gpt-4o-mini",
        "default-embed": "text-embedding-3-small",
    },
    "anthropic": {
        "default-chat": "claude-haiku-4-5",
    },
}

KNOWN_PROVIDERS = frozenset(PROVIDER_CAPABILITIES)


def resolve_model(provider: str, alias_or_id: str) -> str:
    """Resolve a semantic alias (e.g. ``default-chat``) to the provider's model id.

    A value that is not a known alias is returned unchanged.
    """
    return PROVIDER_MODEL_ALIASES.get(provider, {}).get(alias_or_id, alias_or_id)
