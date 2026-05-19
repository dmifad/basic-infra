"""Integration test against a live basic-infra platform (opt-in).

Skipped unless LLM_BASE_URL and LLM_API_KEY are set. Run with::

    LLM_BASE_URL=http://localhost:8013/v1 LLM_API_KEY=tnk_live_... \\
        poetry run pytest -m live
"""
from __future__ import annotations

import os

import pytest

from vams_llm_client import LlmClient

_LIVE = bool(os.getenv("LLM_BASE_URL") and os.getenv("LLM_API_KEY"))
pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(not _LIVE, reason="set LLM_BASE_URL + LLM_API_KEY for live tests"),
]


def test_live_embeddings_and_rerank() -> None:
    client = LlmClient.from_env()
    try:
        emb = client.embeddings.create(model="default-embed", input=["привет", "мир"])
        assert len(emb.vectors) == 2
        assert len(emb.vectors[0]) == 1024

        ranked = client.rerank(
            model="default-rerank",
            query="сеть связи",
            documents=["телекоммуникации и интернет", "парное молоко"],
        )
        scores = [r.relevance_score for r in ranked.results]
        assert scores == sorted(scores, reverse=True)
    finally:
        client.close()


def test_live_chat() -> None:
    client = LlmClient.from_env()
    try:
        resp = client.chat.completions.create(
            model="default-chat",
            messages=[{"role": "user", "content": "Ответь одним словом: да или нет?"}],
            max_tokens=32,
        )
        assert resp.content.strip() != ""
    finally:
        client.close()
