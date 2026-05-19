"""Integration tests — the full gateway over a FastAPI TestClient.

Real SQLite tenant store (temp file); rate limiter fails open (no Redis). No
backends are registered yet, so model dispatch resolves to 404 (Phase 4 wires it).
"""
from __future__ import annotations

from fastapi.testclient import TestClient


def _bearer(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


def test_health_is_unauthenticated_ok(client: TestClient) -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_ready_reports_no_backends(client: TestClient) -> None:
    resp = client.get("/ready")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ready"] is True
    assert body["backends"] == []


def test_models_requires_auth(client: TestClient) -> None:
    resp = client.get("/v1/models")
    assert resp.status_code == 401
    assert resp.json()["error"]["type"] == "authentication_error"


def test_models_rejects_unknown_key(client: TestClient) -> None:
    resp = client.get("/v1/models", headers=_bearer("tnk_live_wrong"))
    assert resp.status_code == 401


def test_models_with_valid_key_returns_empty_list(
    client: TestClient, tenant_key: tuple[str, str]
) -> None:
    _, key = tenant_key
    resp = client.get("/v1/models", headers=_bearer(key))
    assert resp.status_code == 200
    assert resp.json() == {"object": "list", "data": []}


def test_tenants_me(client: TestClient, tenant_key: tuple[str, str]) -> None:
    tenant_id, key = tenant_key
    resp = client.get("/v1/tenants/me", headers=_bearer(key))
    assert resp.status_code == 200
    body = resp.json()
    assert body["tenant_id"] == tenant_id
    assert body["allowed_models"] == ["*"]


def test_x_tenant_id_mismatch_is_forbidden(
    client: TestClient, tenant_key: tuple[str, str]
) -> None:
    _, key = tenant_key
    resp = client.get(
        "/v1/models", headers={**_bearer(key), "X-Tenant-ID": "someone-else"}
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["type"] == "permission_error"


def test_x_tenant_id_match_is_ok(client: TestClient, tenant_key: tuple[str, str]) -> None:
    tenant_id, key = tenant_key
    resp = client.get("/v1/models", headers={**_bearer(key), "X-Tenant-ID": tenant_id})
    assert resp.status_code == 200


def test_chat_unknown_model_returns_404(
    client: TestClient, tenant_key: tuple[str, str]
) -> None:
    _, key = tenant_key
    resp = client.post(
        "/v1/chat/completions",
        headers=_bearer(key),
        json={"model": "t-pro-it-2.1-q8", "messages": [{"role": "user", "content": "hi"}]},
    )
    assert resp.status_code == 404
    error = resp.json()["error"]
    assert error["type"] == "not_found_error"
    assert error["code"] == "model_not_found"


def test_embeddings_unknown_model_returns_404(
    client: TestClient, tenant_key: tuple[str, str]
) -> None:
    _, key = tenant_key
    resp = client.post(
        "/v1/embeddings", headers=_bearer(key), json={"model": "bge-m3", "input": ["x"]}
    )
    assert resp.status_code == 404


def test_rerank_unknown_model_returns_404(
    client: TestClient, tenant_key: tuple[str, str]
) -> None:
    _, key = tenant_key
    resp = client.post(
        "/v1/rerank",
        headers=_bearer(key),
        json={"model": "bge-reranker-v2-m3", "query": "q", "documents": ["d"]},
    )
    assert resp.status_code == 404


def test_completions_unknown_model_returns_404(
    client: TestClient, tenant_key: tuple[str, str]
) -> None:
    _, key = tenant_key
    resp = client.post(
        "/v1/completions", headers=_bearer(key), json={"model": "x", "prompt": "hi"}
    )
    assert resp.status_code == 404


def test_invalid_body_returns_400_envelope(
    client: TestClient, tenant_key: tuple[str, str]
) -> None:
    _, key = tenant_key
    # `messages` is required.
    resp = client.post("/v1/chat/completions", headers=_bearer(key), json={"model": "m"})
    assert resp.status_code == 400
    assert resp.json()["error"]["type"] == "invalid_request_error"


def test_chat_requires_auth(client: TestClient) -> None:
    resp = client.post(
        "/v1/chat/completions",
        json={"model": "m", "messages": [{"role": "user", "content": "hi"}]},
    )
    assert resp.status_code == 401
