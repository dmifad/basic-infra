"""Unit tests — the Bearer-token Authenticator and its cache."""
from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from app.tenancy.auth import Authenticator
from app.tenancy.store import TenantStore


@pytest.fixture
def store(tmp_path: Path) -> Iterator[TenantStore]:
    opened = TenantStore(tmp_path / "t.db")
    yield opened
    opened.close()


def test_authenticate_resolves_tenant(store: TenantStore) -> None:
    _, key = store.create(id="telcoss", display_name="Telcoss")
    auth = Authenticator(store)
    record = auth.authenticate(key)
    assert record is not None and record.id == "telcoss"


def test_authenticate_rejects_unknown_key(store: TenantStore) -> None:
    store.create(id="telcoss", display_name="Telcoss")
    assert Authenticator(store).authenticate("tnk_live_nope") is None


def test_cache_serves_repeated_lookups(store: TenantStore) -> None:
    _, key = store.create(id="cached", display_name="Cached")
    auth = Authenticator(store)
    first = auth.authenticate(key)
    # Soft-delete behind the cache's back: the cached positive result stands
    # until its TTL lapses (acceptable per ADR-0003).
    store.soft_delete("cached")
    second = auth.authenticate(key)
    assert first is not None and second is not None
    assert first.id == second.id == "cached"


def test_expired_cache_entry_is_refreshed(store: TenantStore) -> None:
    _, key = store.create(id="ttl", display_name="Ttl")
    auth = Authenticator(store, cache_ttl=0.0)
    assert auth.authenticate(key) is not None
    store.soft_delete("ttl")
    # TTL is zero -> the next lookup bypasses the cache and sees the deletion.
    assert auth.authenticate(key) is None
