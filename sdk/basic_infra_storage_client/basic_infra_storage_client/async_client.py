"""Асинхронный tenant-scoped клиент хранилища блобов.

Использование:

    from basic_infra_storage_client import AsyncBlobStoreClient

    client = AsyncBlobStoreClient(tenant_id="telcoss")
    ref = await client.put(key="pdf-intake/inbox/doc.pdf", data=pdf_bytes)
    blob = await client.get(key="pdf-intake/inbox/doc.pdf")
    pdf_bytes = await blob.bytes()

Клиент конструирует конкретный адаптер из конфигурации (``StorageSettings``)
один раз при инициализации. После этого все методы автоматически
передают ``tenant_id``, переданный в конструктор.

Cross-tenant операции невозможны через этот клиент. Если нужен доступ
к другому тенанту — создайте отдельный клиент с другим ``tenant_id``.
"""

from __future__ import annotations

from typing import AsyncIterator

from storage.adapters import FilesystemAdapter, MinioAdapter, S3Adapter
from storage.ports.blob_store import (
    BlobData,
    BlobMetadata,
    BlobRef,
    BlobStorePort,
    PresignedOp,
)

from basic_infra_storage_client.config import StorageSettings


class AsyncBlobStoreClient:
    """Tenant-scoped async-клиент хранилища блобов.

    :param tenant_id: идентификатор тенанта. Все операции этого клиента
        работают только в пределах этого тенанта.
    :param settings: опционально — явные настройки. Если не переданы,
        читаются из переменных окружения через ``StorageSettings()``.
    :param backend: опционально — заранее сконструированный backend
        (полезно для тестов с моками).
    """

    def __init__(
        self,
        *,
        tenant_id: str,
        settings: StorageSettings | None = None,
        backend: BlobStorePort | None = None,
    ) -> None:
        if not tenant_id:
            raise ValueError("tenant_id is required")
        self._tenant_id = tenant_id

        if backend is not None:
            self._backend = backend
        else:
            self._backend = self._build_backend(settings or StorageSettings())

    @property
    def tenant_id(self) -> str:
        return self._tenant_id

    @staticmethod
    def _build_backend(settings: StorageSettings) -> BlobStorePort:
        if settings.backend == "filesystem":
            assert settings.filesystem_root is not None  # validated
            return FilesystemAdapter(filesystem_root=settings.filesystem_root)
        if settings.backend == "minio":
            assert settings.bucket and settings.endpoint_url
            assert settings.access_key and settings.secret_key
            return MinioAdapter(
                endpoint_url=settings.endpoint_url,
                bucket=settings.bucket,
                access_key=settings.access_key,
                secret_key=settings.secret_key,
                use_ssl=bool(settings.use_ssl),
                region_name=settings.region,
            )
        if settings.backend == "s3":
            assert settings.bucket is not None
            return S3Adapter(
                bucket=settings.bucket,
                region_name=settings.region,
                access_key=settings.access_key,
                secret_key=settings.secret_key,
            )
        raise ValueError(f"Unknown backend: {settings.backend}")

    # --- Tenant-scoped API ----------------------------------------

    async def put(
        self,
        *,
        key: str,
        data: bytes | AsyncIterator[bytes],
        content_type: str | None = None,
        metadata: dict[str, str] | None = None,
        if_none_match: bool = False,
    ) -> BlobRef:
        return await self._backend.put(
            tenant_id=self._tenant_id,
            key=key,
            data=data,
            content_type=content_type,
            metadata=metadata,
            if_none_match=if_none_match,
        )

    async def get(self, *, key: str) -> BlobData:
        return await self._backend.get(tenant_id=self._tenant_id, key=key)

    async def delete(self, *, key: str) -> None:
        await self._backend.delete(tenant_id=self._tenant_id, key=key)

    async def head(self, *, key: str) -> BlobMetadata | None:
        return await self._backend.head(tenant_id=self._tenant_id, key=key)

    def list(self, *, prefix: str = "") -> AsyncIterator[BlobRef]:
        return self._backend.list(tenant_id=self._tenant_id, prefix=prefix)

    async def presigned_url(
        self,
        *,
        key: str,
        op: PresignedOp,
        ttl_seconds: int = 3600,
        content_type: str | None = None,
    ) -> str:
        return await self._backend.presigned_url(
            tenant_id=self._tenant_id,
            key=key,
            op=op,
            ttl_seconds=ttl_seconds,
            content_type=content_type,
        )
