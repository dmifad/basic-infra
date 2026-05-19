"""Unit tests — capability tables and model-alias resolution."""
from __future__ import annotations

from vams_llm_client.capabilities import (
    KNOWN_PROVIDERS,
    PROVIDER_CAPABILITIES,
    resolve_model,
)


def test_known_providers() -> None:
    assert {"basic-infra", "openai", "anthropic"} == KNOWN_PROVIDERS


def test_basic_infra_supports_everything() -> None:
    assert PROVIDER_CAPABILITIES["basic-infra"] == {"chat", "embed", "rerank", "structured"}


def test_resolve_alias() -> None:
    assert resolve_model("basic-infra", "default-chat") == "t-pro-it-2.1-q8"
    assert resolve_model("openai", "default-embed") == "text-embedding-3-small"


def test_resolve_passes_through_concrete_id() -> None:
    assert resolve_model("basic-infra", "t-pro-it-2.1-q8") == "t-pro-it-2.1-q8"
    assert resolve_model("basic-infra", "unknown-alias") == "unknown-alias"
