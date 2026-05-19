"""Integration test — a request flows HTTP -> gateway -> router -> backend.

Full TestClient over the real app; only the backend HTTP is respx-mocked.
respx patches the default httpx transport, not the TestClient's ASGI transport,
so the client->app hop is real and the app->backend hop is mocked.
"""
from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.tenancy.store import TenantStore

_BACKENDS_YAML = """
backends:
  - name: fake-llama
    kind: openai_compat
    base_url: http://fake-llama:8080/v1
    models:
      - id: t-pro-it-2.1-q8
        backend_model_name: T-pro.gguf
        capabilities: [chat, completions, structured]
  - name: fake-tei
    kind: tei
    base_url: http://fake-tei:80
    models:
      - id: bge-m3
        backend_model_name: BAAI/bge-m3
        capabilities: [embeddings]
"""


@pytest.fixture
def dispatch_client(tmp_path: Path) -> Iterator[tuple[TestClient, str]]:
    """A TestClient with two registered fake backends and one seeded tenant."""
    config = tmp_path / "backends.yaml"
    config.write_text(_BACKENDS_YAML)
    settings = Settings(
        tenant_db_path=tmp_path / "t.db",
        redis_url="redis://127.0.0.1:6390/0",
        backends_config=config,
        backend_health_interval_seconds=3600,  # no probing during the test
        gateway_log_format="console",
    )
    store = TenantStore(settings.tenant_db_path)
    _, key = store.create(id="telcoss", display_name="Telcoss")
    store.close()
    with TestClient(create_app(settings)) as client:
        yield client, key


def test_models_lists_registered_models(dispatch_client: tuple[TestClient, str]) -> None:
    client, key = dispatch_client
    resp = client.get("/v1/models", headers={"Authorization": f"Bearer {key}"})
    assert resp.status_code == 200
    assert {m["id"] for m in resp.json()["data"]} == {"t-pro-it-2.1-q8", "bge-m3"}


@respx.mock
def test_chat_dispatches_to_backend(dispatch_client: tuple[TestClient, str]) -> None:
    client, key = dispatch_client
    respx.post("http://fake-llama:8080/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "c1",
                "object": "chat.completion",
                "created": 1,
                "model": "T-pro.gguf",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "Привет!"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
            },
        )
    )
    resp = client.post(
        "/v1/chat/completions",
        headers={"Authorization": f"Bearer {key}"},
        json={
            "model": "t-pro-it-2.1-q8",
            "messages": [{"role": "user", "content": "Привет"}],
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["model"] == "t-pro-it-2.1-q8"
    assert body["metadata"]["backend"] == "fake-llama"
    assert body["choices"][0]["message"]["content"] == "Привет!"


@respx.mock
def test_embeddings_dispatch_to_backend(dispatch_client: tuple[TestClient, str]) -> None:
    client, key = dispatch_client
    respx.post("http://fake-tei:80/embed").mock(
        return_value=httpx.Response(200, json=[[0.1, 0.2, 0.3]])
    )
    resp = client.post(
        "/v1/embeddings",
        headers={"Authorization": f"Bearer {key}"},
        json={"model": "bge-m3", "input": ["hello"]},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data) == 1
    assert data[0]["embedding"] == [0.1, 0.2, 0.3]
