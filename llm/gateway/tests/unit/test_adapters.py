"""Unit tests — backend adapter request/response translation (respx-mocked HTTP)."""
from __future__ import annotations

import json

import httpx
import pytest
import respx

from app.backends.base import BackendModel
from app.backends.openai_compat import OpenAICompatAdapter
from app.backends.tei import TeiEmbeddingAdapter
from app.backends.tei_rerank import TeiRerankAdapter
from app.exceptions import BackendUnavailableError, InvalidRequestError
from app.schemas.chat import ChatCompletionRequest
from app.schemas.embeddings import EmbeddingRequest
from app.schemas.rerank import RerankRequest

_CHAT_MODEL = BackendModel(
    id="t-pro", backend_model_name="T-pro.gguf", capabilities=frozenset({"chat"})
)
_CHAT_BACKEND_JSON = {
    "id": "cmpl-1",
    "object": "chat.completion",
    "created": 1,
    "model": "T-pro.gguf",
    "choices": [
        {
            "index": 0,
            "message": {"role": "assistant", "content": "ok"},
            "finish_reason": "stop",
        }
    ],
    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
}


def _chat_request() -> ChatCompletionRequest:
    return ChatCompletionRequest.model_validate(
        {"model": "t-pro", "messages": [{"role": "user", "content": "hi"}]}
    )


@respx.mock
async def test_openai_compat_chat_translates() -> None:
    route = respx.post("http://fake:8080/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=_CHAT_BACKEND_JSON)
    )
    adapter = OpenAICompatAdapter(name="llama", base_url="http://fake:8080/v1")
    try:
        resp = await adapter.chat_completion(_chat_request(), _CHAT_MODEL)
    finally:
        await adapter.aclose()
    assert route.called
    # request: the platform model id is swapped for the backend's native name
    sent = json.loads(route.calls.last.request.content)
    assert sent["model"] == "T-pro.gguf"
    # response: platform model id restored, gateway metadata attached
    assert resp.model == "t-pro"
    assert resp.metadata.backend == "llama"
    assert resp.metadata.response_format_fallback is False
    assert resp.choices[0].message.content == "ok"


@respx.mock
async def test_openai_compat_maps_5xx_to_unavailable() -> None:
    respx.post("http://fake:8080/v1/chat/completions").mock(
        return_value=httpx.Response(503)
    )
    adapter = OpenAICompatAdapter(name="llama", base_url="http://fake:8080/v1")
    try:
        with pytest.raises(BackendUnavailableError):
            await adapter.chat_completion(_chat_request(), _CHAT_MODEL)
    finally:
        await adapter.aclose()


@respx.mock
async def test_openai_compat_health_probe() -> None:
    respx.get("http://fake:8080/v1/models").mock(return_value=httpx.Response(200))
    adapter = OpenAICompatAdapter(name="llama", base_url="http://fake:8080/v1")
    try:
        assert await adapter.health() is True
    finally:
        await adapter.aclose()


@respx.mock
async def test_tei_embedding_translates() -> None:
    respx.post("http://tei:80/embed").mock(
        return_value=httpx.Response(200, json=[[0.1, 0.2], [0.3, 0.4]])
    )
    adapter = TeiEmbeddingAdapter(name="tei-embed", base_url="http://tei:80")
    model = BackendModel(
        id="bge-m3", backend_model_name="BAAI/bge-m3", capabilities=frozenset({"embeddings"})
    )
    try:
        resp = await adapter.embedding(EmbeddingRequest(model="bge-m3", input=["a", "b"]), model)
    finally:
        await adapter.aclose()
    assert resp.model == "bge-m3"
    assert len(resp.data) == 2
    assert resp.data[0].embedding == [0.1, 0.2]
    assert resp.data[1].index == 1


@respx.mock
async def test_tei_rerank_translates_sorts_and_truncates() -> None:
    respx.post("http://tei:80/rerank").mock(
        return_value=httpx.Response(
            200, json=[{"index": 0, "score": 0.2}, {"index": 1, "score": 0.9}]
        )
    )
    adapter = TeiRerankAdapter(name="tei-rerank", base_url="http://tei:80")
    model = BackendModel(
        id="bge-rr", backend_model_name="BAAI/bge-reranker", capabilities=frozenset({"rerank"})
    )
    try:
        resp = await adapter.rerank(
            RerankRequest(model="bge-rr", query="q", documents=["d0", "d1"], top_n=1), model
        )
    finally:
        await adapter.aclose()
    assert len(resp.results) == 1  # truncated to top_n
    assert resp.results[0].index == 1  # highest score first
    assert resp.results[0].relevance_score == 0.9


async def test_tei_embedding_rejects_chat() -> None:
    """An adapter raises for a capability its kind does not serve."""
    adapter = TeiEmbeddingAdapter(name="tei-embed", base_url="http://tei:80")
    try:
        with pytest.raises(InvalidRequestError):
            await adapter.chat_completion(_chat_request(), _CHAT_MODEL)
    finally:
        await adapter.aclose()
