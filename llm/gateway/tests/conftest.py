"""Shared pytest fixtures for the gateway test suite."""
from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.tenancy.store import TenantStore


@pytest.fixture
def tmp_settings(tmp_path: Path) -> Settings:
    """Settings pointing at a throwaway tenant DB and an unreachable Redis.

    The unreachable Redis exercises the rate limiter's fail-open path, so API
    tests are not coupled to a running Redis.
    """
    return Settings(
        tenant_db_path=tmp_path / "tenants.db",
        redis_url="redis://127.0.0.1:6390/0",
        rate_limit_fail_open=True,
        gateway_log_format="console",
    )


@pytest.fixture
def store(tmp_settings: Settings) -> Iterator[TenantStore]:
    """An open tenant store at the temp settings' DB path."""
    opened = TenantStore(tmp_settings.tenant_db_path)
    yield opened
    opened.close()


@pytest.fixture
def tenant_key(store: TenantStore) -> tuple[str, str]:
    """Seed one tenant and return ``(tenant_id, raw_api_key)``."""
    record, key = store.create(id="test-tenant", display_name="Test Tenant")
    return record.id, key


@pytest.fixture
def client(tmp_settings: Settings, tenant_key: tuple[str, str]) -> Iterator[TestClient]:
    """A TestClient over an app whose tenant DB already has ``test-tenant`` seeded."""
    with TestClient(create_app(tmp_settings)) as test_client:
        yield test_client
