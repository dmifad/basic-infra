"""Smoke-тесты AsyncBlobStoreClient.

Проверяем, что tenant-scoped обёртка корректно делегирует в порт и
что cross-tenant изоляция работает на уровне SDK.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from basic_infra_storage_client import AsyncBlobStoreClient
from storage.adapters.filesystem import FilesystemAdapter
from storage.ports.exceptions import BlobNotFound

pytestmark = pytest.mark.asyncio


async def test_client_is_tenant_scoped(tmp_path: Path) -> None:
    adapter = FilesystemAdapter(filesystem_root=tmp_path)

    telcoss = AsyncBlobStoreClient(tenant_id="telcoss", backend=adapter)
    pamyat = AsyncBlobStoreClient(tenant_id="pamyat", backend=adapter)

    await telcoss.put(key="shared-name.txt", data=b"telcoss-data")
    await pamyat.put(key="shared-name.txt", data=b"pamyat-data")

    # Тот же key, разные тенанты — разные данные.
    telcoss_blob = await telcoss.get(key="shared-name.txt")
    pamyat_blob = await pamyat.get(key="shared-name.txt")

    assert await telcoss_blob.bytes() == b"telcoss-data"
    assert await pamyat_blob.bytes() == b"pamyat-data"


async def test_empty_tenant_id_rejected(tmp_path: Path) -> None:
    adapter = FilesystemAdapter(filesystem_root=tmp_path)
    with pytest.raises(ValueError):
        AsyncBlobStoreClient(tenant_id="", backend=adapter)


async def test_delete_then_get_raises(tmp_path: Path) -> None:
    adapter = FilesystemAdapter(filesystem_root=tmp_path)
    client = AsyncBlobStoreClient(tenant_id="telcoss", backend=adapter)

    await client.put(key="k.txt", data=b"v")
    await client.delete(key="k.txt")

    with pytest.raises(BlobNotFound):
        await client.get(key="k.txt")
