"""Unit tests — SQLite tenant store CRUD, key rotation, soft delete."""
from __future__ import annotations

from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path

import pytest

from app.tenancy.store import TenantExists, TenantNotFound, TenantStore


@pytest.fixture
def store(tmp_path: Path) -> Iterator[TenantStore]:
    opened = TenantStore(tmp_path / "t.db")
    yield opened
    opened.close()


def test_create_and_authenticate(store: TenantStore) -> None:
    record, key = store.create(id="telcoss", display_name="Telcoss")
    assert record.id == "telcoss"
    assert record.allowed_models == ("*",)
    assert key.startswith("tnk_live_")
    assert store.authenticate(key) is not None
    assert store.authenticate("tnk_live_wrong") is None


def test_duplicate_create_raises(store: TenantStore) -> None:
    store.create(id="dup", display_name="Dup")
    with pytest.raises(TenantExists):
        store.create(id="dup", display_name="Dup again")


def test_list_excludes_deleted_by_default(store: TenantStore) -> None:
    store.create(id="a", display_name="A")
    store.create(id="b", display_name="B")
    store.soft_delete("b")
    assert [t.id for t in store.list()] == ["a"]
    assert {t.id for t in store.list(include_deleted=True)} == {"a", "b"}


def test_rotate_key_keeps_old_within_grace(store: TenantStore) -> None:
    _, old_key = store.create(id="rot", display_name="Rot")
    new_key = store.rotate_key("rot")
    assert new_key != old_key
    assert store.authenticate(new_key) is not None
    # Old key still works inside the 24 h grace window.
    assert store.authenticate(old_key) is not None


def test_rotated_key_expires_after_grace(tmp_path: Path) -> None:
    expired = TenantStore(tmp_path / "g.db", grace_period=timedelta(seconds=-10))
    try:
        _, old_key = expired.create(id="exp", display_name="Exp")
        new_key = expired.rotate_key("exp")
        assert expired.authenticate(new_key) is not None
        # Grace window already elapsed -> old key no longer authenticates.
        assert expired.authenticate(old_key) is None
    finally:
        expired.close()


def test_soft_delete_blocks_auth(store: TenantStore) -> None:
    _, key = store.create(id="del", display_name="Del")
    store.soft_delete("del")
    assert store.authenticate(key) is None
    with pytest.raises(TenantNotFound):
        store.soft_delete("del")


def test_rotate_missing_tenant_raises(store: TenantStore) -> None:
    with pytest.raises(TenantNotFound):
        store.rotate_key("ghost")
