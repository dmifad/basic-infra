"""Unit tests — the embedding cache (standalone, and via the client)."""
from __future__ import annotations

from pathlib import Path

import httpx
import respx

from vams_llm_client import LlmClient
from vams_llm_client.cache import EmbeddingCache

_BASE = "http://gw.test/v1"


def test_cache_roundtrip(tmp_path: Path) -> None:
    cache = EmbeddingCache(str(tmp_path))
    assert cache.get("basic-infra", "bge-m3", "hello") is None
    cache.put("basic-infra", "bge-m3", "hello", [0.1, 0.2])
    assert cache.get("basic-infra", "bge-m3", "hello") == [0.1, 0.2]
    # The key includes the model — a different model is a miss.
    assert cache.get("basic-infra", "other-model", "hello") is None
    cache.close()


def _embed_response() -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "object": "list",
            "model": "bge-m3",
            "data": [
                {"object": "embedding", "index": 0, "embedding": [0.1]},
                {"object": "embedding", "index": 1, "embedding": [0.2]},
            ],
            "usage": {"prompt_tokens": 1, "total_tokens": 1},
        },
    )


@respx.mock
def test_client_cache_skips_refetch(tmp_path: Path) -> None:
    route = respx.post(f"{_BASE}/embeddings").mock(return_value=_embed_response())
    client = LlmClient(
        provider="basic-infra", base_url=_BASE, api_key="k", cache_dir=str(tmp_path)
    )
    client.embeddings.cache_enabled = True
    first = client.embeddings.create(model="bge-m3", input=["a", "b"])
    second = client.embeddings.create(model="bge-m3", input=["a", "b"])
    client.close()
    assert first.vectors == second.vectors == [[0.1], [0.2]]
    assert route.call_count == 1  # second call served entirely from cache


@respx.mock
def test_client_cache_off_by_default(tmp_path: Path) -> None:
    route = respx.post(f"{_BASE}/embeddings").mock(return_value=_embed_response())
    client = LlmClient(
        provider="basic-infra", base_url=_BASE, api_key="k", cache_dir=str(tmp_path)
    )
    client.embeddings.create(model="bge-m3", input=["a", "b"])
    client.embeddings.create(model="bge-m3", input=["a", "b"])
    client.close()
    assert route.call_count == 2  # cache_enabled is False -> every call hits the platform
