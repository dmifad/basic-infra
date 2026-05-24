"""Синхронный tenant-scoped клиент хранилища блобов.

Тонкая обёртка над ``AsyncBlobStoreClient`` для синхронного кода
(скрипты, миграции, CLI). Внутри использует ``asyncio.run``.

Использовать в asyncio-event-loop коде НЕЛЬЗЯ — для этого
``AsyncBlobStoreClient``.
"""

from __future__ import annotations

import asyncio
from typing import Iterator

from storage.ports.blob_store import (
    BlobMetadata,
    BlobRef,
    BlobStorePort,
    PresignedOp,
)

from basic_infra_storage_client.async_client import AsyncBlobStoreClient
from basic_infra_storage_client.config import StorageSettings


class BlobStoreClient:
    """Tenant-scoped sync-клиент хранилища блобов.

    Семантика та же, что у ``AsyncBlobStoreClient``, но методы синхронные.
    ``get`` возвращает ``bytes`` сразу (без BlobData), потому что
    стриминг в синхронном API не имеет смысла.
    """

    def __init__(
        self,
        *,
        tenant_id: str,
        settings: StorageSettings | None = None,
        backend: BlobStorePort | None = None,
    ) -> None:
        self._async = AsyncBlobStoreClient(
            tenant_id=tenant_id, settings=settings, backend=backend
        )

    @property
    def tenant_id(self) -> str:
        return self._async.tenant_id

    def put(
        self,
        *,
        key: str,
        data: bytes,
        content_type: str | None = None,
        metadata: dict[str, str] | None = None,
        if_none_match: bool = False,
    ) -> BlobRef:
        return asyncio.run(
            self._async.put(
                key=key,
                data=data,
                content_type=content_type,
                metadata=metadata,
                if_none_match=if_none_match,
            )
        )

    def get(self, *, key: str) -> bytes:
        async def _read() -> bytes:
            blob = await self._async.get(key=key)
            return await blob.bytes()

        return asyncio.run(_read())

    def delete(self, *, key: str) -> None:
        asyncio.run(self._async.delete(key=key))

    def head(self, *, key: str) -> BlobMetadata | None:
        return asyncio.run(self._async.head(key=key))

    def list(self, *, prefix: str = "") -> Iterator[BlobRef]:
        async def _collect() -> list[BlobRef]:
            return [ref async for ref in self._async.list(prefix=prefix)]

        return iter(asyncio.run(_collect()))

    def presigned_url(
        self,
        *,
        key: str,
        op: PresignedOp,
        ttl_seconds: int = 3600,
        content_type: str | None = None,
    ) -> str:
        return asyncio.run(
            self._async.presigned_url(
                key=key,
                op=op,
                ttl_seconds=ttl_seconds,
                content_type=content_type,
            )
        )
