"""Integration tests — background health checker and /ready aggregation."""
from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.routing.health import HealthChecker
from app.routing.registry import BackendConfig, BackendsConfig, ModelConfig, Registry

# An address nothing listens on — health probes against it fail fast.
_DEAD_URL = "http://127.0.0.1:6399/v1"

_DEAD_YAML = f"""
backends:
  - name: dead-backend
    kind: openai_compat
    base_url: {_DEAD_URL}
    models:
      - id: ghost
        backend_model_name: ghost.gguf
        capabilities: [chat]
"""


async def test_check_once_marks_unhealthy_after_threshold() -> None:
    registry = Registry.from_config(
        BackendsConfig(
            backends=[
                BackendConfig(
                    name="dead",
                    kind="openai_compat",
                    base_url=_DEAD_URL,
                    models=[
                        ModelConfig(
                            id="ghost", backend_model_name="g", capabilities=["chat"]
                        )
                    ],
                )
            ]
        )
    )
    checker = HealthChecker(registry, interval_seconds=3600, unhealthy_threshold=3)
    adapter = registry.adapters[0]
    try:
        assert adapter.is_healthy  # optimistic before the first probe
        await checker.check_once()
        assert adapter.is_healthy and adapter.consecutive_failures == 1
        await checker.check_once()
        await checker.check_once()
        assert not adapter.is_healthy  # three consecutive failures
        assert adapter.consecutive_failures == 3
    finally:
        await registry.aclose()


def test_ready_returns_503_when_a_backend_is_unhealthy(tmp_path: Path) -> None:
    config = tmp_path / "backends.yaml"
    config.write_text(_DEAD_YAML)
    settings = Settings(
        tenant_db_path=tmp_path / "t.db",
        redis_url="redis://127.0.0.1:6390/0",
        backends_config=config,
        backend_health_interval_seconds=3600,
        backend_unhealthy_threshold=3,
        gateway_log_format="console",
    )
    app = create_app(settings)
    with TestClient(app) as client:
        # Backends start optimistically healthy.
        assert client.get("/ready").status_code == 200

        registry: Registry = app.state.registry
        for adapter in registry.adapters:
            for _ in range(3):
                adapter.record_health(False, unhealthy_threshold=3)

        resp = client.get("/ready")
        assert resp.status_code == 503
        body = resp.json()
        assert body["ready"] is False
        assert body["backends"][0]["name"] == "dead-backend"
        assert body["backends"][0]["healthy"] is False
