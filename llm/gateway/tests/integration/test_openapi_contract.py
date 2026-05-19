"""Integration test — the live app honours the documented OpenAPI contract.

``docs/api/openapi.yaml`` is the single source of truth (ADR-0002). Every path
it documents must actually be served by the FastAPI app.
"""
from __future__ import annotations

from pathlib import Path

import yaml
from fastapi.testclient import TestClient

_SPEC_PATH = Path(__file__).resolve().parents[4] / "docs" / "api" / "openapi.yaml"


def test_documented_paths_are_all_served(client: TestClient) -> None:
    spec = yaml.safe_load(_SPEC_PATH.read_text())
    documented = set(spec["paths"])
    served = set(client.get("/openapi.json").json()["paths"])
    missing = documented - served
    assert not missing, f"documented paths not served by the app: {sorted(missing)}"
