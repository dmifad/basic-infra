"""Integration tests — the router dispatching through registry + adapters.

Backend HTTP is respx-mocked; everything else (registry, router, adapters) is
real, so this exercises the full resolve → authorize → dispatch path.
"""
from __future__ import annotations

import httpx
import pytest
import respx

from app.exceptions import (
    BackendUnavailableError,
    ForbiddenError,
    InvalidRequestError,
    ModelNotFoundError,
)
from app.routing.registry import BackendConfig, BackendsConfig, ModelConfig, Registry
from app.routing.router import Router
from app.schemas.chat import ChatCompletionRequest
from app.schemas.embeddings import EmbeddingRequest
from app.tenancy.store import TenantRecord

_WILDCARD_TENANT = TenantRecord(id="telcoss", display_name="T", allowed_models=("*",))

_CHAT_JSON = {
    "id": "c1",
    "object": "chat.completion",
    "created": 1,
    "model": "T.gguf",
    "choices": [
        {"index": 0, "message": {"role": "assistant", "content": "hi"}, "finish_reason": "stop"}
    ],
    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
}


def _registry() -> Registry:
    return Registry.from_config(
        BackendsConfig(
            backends=[
                BackendConfig(
                    name="llama",
                    kind="openai_compat",
                    base_url="http://tpro:8080/v1",
                    models=[
                        ModelConfig(
                            id="t-pro",
                            backend_model_name="T.gguf",
                            capabilities=["chat", "completions", "structured"],
                        )
                    ],
                ),
                BackendConfig(
                    name="tei",
                    kind="tei",
                    base_url="http://tei:80",
                    models=[
                        ModelConfig(
                            id="bge-m3",
                            backend_model_name="BAAI/bge-m3",
                            capabilities=["embeddings"],
                        )
                    ],
                ),
            ]
        )
    )


def _chat(model: str) -> ChatCompletionRequest:
    return ChatCompletionRequest.model_validate(
        {"model": model, "messages": [{"role": "user", "content": "x"}]}
    )


@respx.mock
async def test_router_dispatches_chat() -> None:
    respx.post("http://tpro:8080/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=_CHAT_JSON)
    )
    registry = _registry()
    try:
        resp = await Router(registry).chat_completion(_chat("t-pro"), _WILDCARD_TENANT)
    finally:
        await registry.aclose()
    assert resp.metadata.backend == "llama"
    assert resp.choices[0].message.content == "hi"


@respx.mock
async def test_router_dispatches_embedding() -> None:
    respx.post("http://tei:80/embed").mock(
        return_value=httpx.Response(200, json=[[0.1, 0.2]])
    )
    registry = _registry()
    try:
        resp = await Router(registry).embedding(
            EmbeddingRequest(model="bge-m3", input="x"), _WILDCARD_TENANT
        )
    finally:
        await registry.aclose()
    assert len(resp.data) == 1


async def test_router_unknown_model_raises_404() -> None:
    registry = _registry()
    try:
        with pytest.raises(ModelNotFoundError):
            await Router(registry).chat_completion(_chat("ghost"), _WILDCARD_TENANT)
    finally:
        await registry.aclose()


async def test_router_capability_mismatch_raises_400() -> None:
    """bge-m3 is embeddings-only — a chat request against it is a 400."""
    registry = _registry()
    try:
        with pytest.raises(InvalidRequestError):
            await Router(registry).chat_completion(_chat("bge-m3"), _WILDCARD_TENANT)
    finally:
        await registry.aclose()


async def test_router_tenant_not_allowed_raises_403() -> None:
    registry = _registry()
    limited = TenantRecord(id="pamyat", display_name="P", allowed_models=("bge-m3",))
    try:
        with pytest.raises(ForbiddenError):
            await Router(registry).chat_completion(_chat("t-pro"), limited)
    finally:
        await registry.aclose()


async def test_router_unhealthy_backend_raises_503() -> None:
    registry = _registry()
    adapter, _ = registry.get_backend_for("t-pro")
    for _ in range(3):
        adapter.record_health(False, unhealthy_threshold=3)
    try:
        with pytest.raises(BackendUnavailableError):
            await Router(registry).chat_completion(_chat("t-pro"), _WILDCARD_TENANT)
    finally:
        await registry.aclose()
