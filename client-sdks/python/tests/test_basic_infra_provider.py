"""Unit tests — the basic-infra provider's HTTP translation (respx-mocked)."""
from __future__ import annotations

import httpx
import pytest
import respx

from vams_llm_client.errors import PlatformError
from vams_llm_client.providers.basic_infra import BasicInfraProvider

_BASE = "http://gw.test/v1"


@respx.mock
def test_chat_completion() -> None:
    respx.post(f"{_BASE}/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "c1",
                "object": "chat.completion",
                "created": 1,
                "model": "t-pro-it-2.1-q8",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "привет"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
                "metadata": {"backend": "llama-cpp-tpro"},
            },
        )
    )
    provider = BasicInfraProvider(base_url=_BASE, api_key="k")
    try:
        resp = provider.chat_completion(
            model="t-pro-it-2.1-q8", messages=[{"role": "user", "content": "hi"}]
        )
    finally:
        provider.close()
    assert resp.content == "привет"
    assert resp.choices[0].finish_reason == "stop"


@respx.mock
def test_embeddings() -> None:
    respx.post(f"{_BASE}/embeddings").mock(
        return_value=httpx.Response(
            200,
            json={
                "object": "list",
                "model": "bge-m3",
                "data": [
                    {"object": "embedding", "index": 0, "embedding": [0.1, 0.2]},
                    {"object": "embedding", "index": 1, "embedding": [0.3, 0.4]},
                ],
                "usage": {"prompt_tokens": 2, "total_tokens": 2},
            },
        )
    )
    provider = BasicInfraProvider(base_url=_BASE, api_key="k")
    try:
        resp = provider.embeddings(model="bge-m3", inputs=["a", "b"])
    finally:
        provider.close()
    assert resp.vectors == [[0.1, 0.2], [0.3, 0.4]]


@respx.mock
def test_rerank_flattens_document_text() -> None:
    respx.post(f"{_BASE}/rerank").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "r1",
                "object": "rerank",
                "model": "bge-reranker-v2-m3",
                "results": [
                    {"index": 1, "relevance_score": 0.9, "document": {"text": "d1"}},
                    {"index": 0, "relevance_score": 0.1, "document": {"text": "d0"}},
                ],
            },
        )
    )
    provider = BasicInfraProvider(base_url=_BASE, api_key="k")
    try:
        resp = provider.rerank(model="bge-reranker-v2-m3", query="q", documents=["d0", "d1"])
    finally:
        provider.close()
    assert resp.results[0].index == 1
    assert resp.results[0].document == "d1"


@respx.mock
def test_error_envelope_becomes_platform_error() -> None:
    respx.post(f"{_BASE}/chat/completions").mock(
        return_value=httpx.Response(
            404, json={"error": {"message": "Model not found: x", "type": "not_found_error"}}
        )
    )
    provider = BasicInfraProvider(base_url=_BASE, api_key="k")
    try:
        with pytest.raises(PlatformError) as caught:
            provider.chat_completion(model="x", messages=[{"role": "user", "content": "hi"}])
        assert caught.value.status_code == 404
        assert "Model not found" in str(caught.value)
    finally:
        provider.close()
