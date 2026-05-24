"""Тесты FilesystemAdapter.

Покрываем happy paths и инварианты безопасности (изоляция тенантов).
Полная матрица — задача отдельной test-сессии.
"""

from __future__ import annotations

from pathlib import Path
from typing import AsyncIterator

import pytest

from storage.adapters.filesystem import FilesystemAdapter
from storage.ports.exceptions import (
    BlobAlreadyExists,
    BlobNotFound,
    BlobStoreConfigError,
    BlobStoreError,
    TenantIsolationError,
)


pytestmark = pytest.mark.asyncio


async def test_put_then_get_returns_same_bytes(
    filesystem_adapter: FilesystemAdapter, sample_tenant: str
) -> None:
    payload = b"hello world"
    ref = await filesystem_adapter.put(
        tenant_id=sample_tenant,
        key="docs/a.txt",
        data=payload,
        content_type="text/plain",
    )
    assert ref.size == len(payload)
    assert ref.content_type == "text/plain"

    blob = await filesystem_adapter.get(
        tenant_id=sample_tenant, key="docs/a.txt"
    )
    assert await blob.bytes() == payload


async def test_get_missing_raises_blob_not_found(
    filesystem_adapter: FilesystemAdapter, sample_tenant: str
) -> None:
    with pytest.raises(BlobNotFound):
        await filesystem_adapter.get(
            tenant_id=sample_tenant, key="missing.txt"
        )


async def test_head_missing_returns_none(
    filesystem_adapter: FilesystemAdapter, sample_tenant: str
) -> None:
    assert (
        await filesystem_adapter.head(
            tenant_id=sample_tenant, key="missing.txt"
        )
        is None
    )


async def test_delete_is_idempotent(
    filesystem_adapter: FilesystemAdapter, sample_tenant: str
) -> None:
    # Удаление несуществующего — без исключения.
    await filesystem_adapter.delete(
        tenant_id=sample_tenant, key="never-existed.txt"
    )

    await filesystem_adapter.put(
        tenant_id=sample_tenant, key="x.txt", data=b"x"
    )
    await filesystem_adapter.delete(tenant_id=sample_tenant, key="x.txt")
    await filesystem_adapter.delete(tenant_id=sample_tenant, key="x.txt")

    assert (
        await filesystem_adapter.head(tenant_id=sample_tenant, key="x.txt")
    ) is None


async def test_if_none_match_blocks_overwrite(
    filesystem_adapter: FilesystemAdapter, sample_tenant: str
) -> None:
    await filesystem_adapter.put(
        tenant_id=sample_tenant, key="k.txt", data=b"v1"
    )
    with pytest.raises(BlobAlreadyExists):
        await filesystem_adapter.put(
            tenant_id=sample_tenant,
            key="k.txt",
            data=b"v2",
            if_none_match=True,
        )


async def test_list_returns_only_tenant_keys(
    filesystem_adapter: FilesystemAdapter,
) -> None:
    await filesystem_adapter.put(
        tenant_id="telcoss", key="a.txt", data=b"a"
    )
    await filesystem_adapter.put(
        tenant_id="telcoss", key="dir/b.txt", data=b"b"
    )
    await filesystem_adapter.put(
        tenant_id="pamyat", key="c.txt", data=b"c"
    )

    keys = [ref.key async for ref in filesystem_adapter.list(tenant_id="telcoss")]
    assert sorted(keys) == ["a.txt", "dir/b.txt"]


async def test_list_with_prefix(
    filesystem_adapter: FilesystemAdapter, sample_tenant: str
) -> None:
    await filesystem_adapter.put(
        tenant_id=sample_tenant, key="inbox/a.txt", data=b"a"
    )
    await filesystem_adapter.put(
        tenant_id=sample_tenant, key="outbox/b.txt", data=b"b"
    )

    keys = [
        ref.key
        async for ref in filesystem_adapter.list(
            tenant_id=sample_tenant, prefix="inbox/"
        )
    ]
    assert keys == ["inbox/a.txt"]


async def test_path_traversal_in_key_rejected(
    filesystem_adapter: FilesystemAdapter, sample_tenant: str
) -> None:
    with pytest.raises(TenantIsolationError):
        await filesystem_adapter.put(
            tenant_id=sample_tenant,
            key="../other-tenant/secret.txt",
            data=b"x",
        )


async def test_absolute_key_rejected(
    filesystem_adapter: FilesystemAdapter, sample_tenant: str
) -> None:
    with pytest.raises(TenantIsolationError):
        await filesystem_adapter.put(
            tenant_id=sample_tenant, key="/etc/passwd", data=b"x"
        )


async def test_invalid_tenant_id_rejected(
    filesystem_adapter: FilesystemAdapter,
) -> None:
    for bad in ("", "..", ".", "with/slash"):
        with pytest.raises(TenantIsolationError):
            await filesystem_adapter.put(
                tenant_id=bad, key="x.txt", data=b"x"
            )


async def test_presigned_url_not_supported(
    filesystem_adapter: FilesystemAdapter, sample_tenant: str
) -> None:
    with pytest.raises(BlobStoreError):
        await filesystem_adapter.presigned_url(
            tenant_id=sample_tenant, key="k.txt", op="GET"
        )


async def test_nonexistent_root_rejected(tmp_path: Path) -> None:
    with pytest.raises(BlobStoreConfigError):
        FilesystemAdapter(filesystem_root=tmp_path / "does-not-exist")


async def test_streaming_put_and_get(
    filesystem_adapter: FilesystemAdapter, sample_tenant: str
) -> None:
    async def chunks() -> AsyncIterator[bytes]:
        yield b"chunk1"
        yield b"chunk2"
        yield b"chunk3"

    ref = await filesystem_adapter.put(
        tenant_id=sample_tenant, key="big.bin", data=chunks()
    )
    assert ref.size == len(b"chunk1chunk2chunk3")

    blob = await filesystem_adapter.get(
        tenant_id=sample_tenant, key="big.bin"
    )
    collected = b""
    async for c in blob.stream():
        collected += c
    assert collected == b"chunk1chunk2chunk3"


async def test_existing_file_without_meta_is_readable(
    filesystem_adapter: FilesystemAdapter,
    filesystem_root: Path,
    sample_tenant: str,
) -> None:
    """pdf-intake adoption: файлы, существующие до SDK, должны читаться.

    Это критичный инвариант фазы 1 миграции — см. runbook §1.
    """
    # Эмулируем «pre-SDK» файл: лежит в tenant-директории, без .meta.json.
    tenant_dir = filesystem_root / sample_tenant
    tenant_dir.mkdir(parents=True, exist_ok=True)
    legacy_file = tenant_dir / "legacy.txt"
    legacy_file.write_bytes(b"legacy content")

    # head должен реконструировать метаданные.
    meta = await filesystem_adapter.head(
        tenant_id=sample_tenant, key="legacy.txt"
    )
    assert meta is not None
    assert meta.size == len(b"legacy content")
    assert meta.etag  # вычислен как sha256

    # get должен прочитать содержимое.
    blob = await filesystem_adapter.get(
        tenant_id=sample_tenant, key="legacy.txt"
    )
    assert await blob.bytes() == b"legacy content"
