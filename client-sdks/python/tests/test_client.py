"""Unit tests — LlmClient construction, provider selection, capability gating."""
from __future__ import annotations

import pytest

from vams_llm_client import LlmClient
from vams_llm_client.errors import CapabilityNotAvailable, ProviderNotConfigured


def test_unknown_provider_rejected() -> None:
    with pytest.raises(ProviderNotConfigured):
        LlmClient(provider="nonsense")


def test_basic_infra_requires_url_and_key() -> None:
    with pytest.raises(ProviderNotConfigured):
        LlmClient(provider="basic-infra")


def test_capabilities_basic_infra() -> None:
    client = LlmClient(provider="basic-infra", base_url="http://x/v1", api_key="k")
    assert client.capabilities() == {"chat": True, "embed": True, "rerank": True}
    client.close()


def test_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "basic-infra")
    monkeypatch.setenv("LLM_BASE_URL", "http://x/v1")
    monkeypatch.setenv("LLM_API_KEY", "k")
    client = LlmClient.from_env()
    assert client.provider == "basic-infra"
    client.close()


def test_anthropic_reports_no_rerank_and_blocks_it() -> None:
    client = LlmClient(provider="anthropic", api_key="sk-ant-test")
    assert client.capabilities()["rerank"] is False
    assert client.capabilities()["embed"] is False
    with pytest.raises(CapabilityNotAvailable):
        client.rerank(model="default-rerank", query="q", documents=["d"])
    client.close()
