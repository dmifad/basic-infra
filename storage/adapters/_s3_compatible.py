"""Базовый адаптер для S3-совместимых хранилищ.

Используется как общая основа для `MinioAdapter` и `S3Adapter`.
Различаются они только тем, как создаётся клиент `aiobotocore`
(endpoint URL, регион, способ аутентификации).

Раскладка ключей: `{tenant_id}/{key}` внутри единого bucket'а.
Один bucket на окружение (см. ADR-0010).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, AsyncIterator, Final

from aiobotocore.session import AioSession
from botocore.exceptions import ClientError

from storage.ports.blob_store import (
    BlobData,
    BlobMetadata,
    BlobRef,
    BlobStorePort,
    PresignedOp,
)
from storage.ports.exceptions import (
    BlobAlreadyExists,
    BlobNotFound,
    BlobStoreError,
    BlobStoreUnavailable,
    TenantIsolationError,
)

_TENANT_KEY_SEPARATOR: Final = "/"


class _S3BlobData(BlobData):
    """BlobData для S3-совместимых backend'ов.

    Хранит ссылку на raw streaming body из aiobotocore и итерирует
    его при вызове `.stream()`.
    """

    def __init__(
        self,
        *,
        body: Any,  # aiobotocore StreamingBody
        chunk_size: int = 1024 * 1024,
        **kwargs: object,
    ) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self._body = body
        self._chunk_size = chunk_size

    async def stream(self) -> AsyncIterator[bytes]:
        # aiobotocore's StreamingBody.__aenter__ returns the wrapped aiohttp
        # ClientResponse (no iter_chunks); iter_chunks lives on the body itself.
        async with self._body:
            async for chunk in self._body.iter_chunks(self._chunk_size):
                yield chunk


class _S3CompatibleAdapter(BlobStorePort):
    """Общая реализация для MinIO и AWS S3."""

    def __init__(
        self,
        *,
        bucket: str,
        endpoint_url: str | None = None,
        region_name: str | None = None,
        access_key: str | None = None,
        secret_key: str | None = None,
        use_ssl: bool = True,
    ) -> None:
        self._bucket = bucket
        self._endpoint_url = endpoint_url
        self._region_name = region_name
        self._access_key = access_key
        self._secret_key = secret_key
        self._use_ssl = use_ssl
        self._session = AioSession()

    # --- Утилиты ----------------------------------------------------

    def _client(self) -> Any:
        """Создать async context manager S3-клиента.

        Каждая операция открывает свой клиент. aiobotocore-клиенты
        дешёвые в создании и должны быть закрыты после использования.
        """
        return self._session.create_client(
            "s3",
            endpoint_url=self._endpoint_url,
            region_name=self._region_name,
            aws_access_key_id=self._access_key,
            aws_secret_access_key=self._secret_key,
            use_ssl=self._use_ssl,
        )

    @staticmethod
    def _object_key(tenant_id: str, key: str) -> str:
        if not tenant_id or _TENANT_KEY_SEPARATOR in tenant_id:
            raise TenantIsolationError(
                f"Invalid tenant_id: {tenant_id!r}"
            )
        if key.startswith(_TENANT_KEY_SEPARATOR):
            raise TenantIsolationError(
                f"Key must not start with '/': {key!r}"
            )
        return f"{tenant_id}{_TENANT_KEY_SEPARATOR}{key}"

    @staticmethod
    def _strip_tenant(tenant_id: str, object_key: str) -> str:
        prefix = f"{tenant_id}{_TENANT_KEY_SEPARATOR}"
        if not object_key.startswith(prefix):
            raise TenantIsolationError(
                f"Object key {object_key!r} does not belong to tenant {tenant_id!r}"
            )
        return object_key[len(prefix):]

    # --- BlobStorePort ---------------------------------------------

    async def put(
        self,
        *,
        tenant_id: str,
        key: str,
        data: bytes | AsyncIterator[bytes],
        content_type: str | None = None,
        metadata: dict[str, str] | None = None,
        if_none_match: bool = False,
    ) -> BlobRef:
        object_key = self._object_key(tenant_id, key)

        # aiobotocore put_object принимает bytes или file-like.
        # Для AsyncIterator придётся буферизовать (multipart — out of scope).
        if not isinstance(data, bytes):
            chunks: list[bytes] = []
            async for chunk in data:
                chunks.append(chunk)
            body = b"".join(chunks)
        else:
            body = data

        put_kwargs: dict[str, Any] = {
            "Bucket": self._bucket,
            "Key": object_key,
            "Body": body,
        }
        if content_type:
            put_kwargs["ContentType"] = content_type
        if metadata:
            put_kwargs["Metadata"] = metadata
        if if_none_match:
            # S3-style if-none-match: "*" matches any existing object.
            put_kwargs["IfNoneMatch"] = "*"

        try:
            async with self._client() as client:
                response = await client.put_object(**put_kwargs)
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code")
            if code in ("PreconditionFailed", "412"):
                raise BlobAlreadyExists(tenant_id=tenant_id, key=key) from exc
            raise BlobStoreUnavailable(
                f"S3 put_object failed: {exc}"
            ) from exc

        return BlobRef(
            tenant_id=tenant_id,
            key=key,
            etag=response["ETag"].strip('"'),
            size=len(body),
            content_type=content_type,
        )

    async def get(self, *, tenant_id: str, key: str) -> BlobData:
        object_key = self._object_key(tenant_id, key)
        try:
            client_ctx = self._client()
            client = await client_ctx.__aenter__()
            try:
                response = await client.get_object(
                    Bucket=self._bucket, Key=object_key
                )
            except Exception:
                await client_ctx.__aexit__(None, None, None)
                raise
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code")
            if code in ("NoSuchKey", "404"):
                raise BlobNotFound(tenant_id=tenant_id, key=key) from exc
            raise BlobStoreUnavailable(
                f"S3 get_object failed: {exc}"
            ) from exc

        # NOTE: client держится открытым на время чтения body. Закрывается
        # после исчерпания stream. Это компромисс ради простоты — в проде
        # стоит обернуть в явный async context manager.
        body = response["Body"]
        return _S3BlobData(
            body=body,
            tenant_id=tenant_id,
            key=key,
            size=response["ContentLength"],
            content_type=response.get("ContentType"),
            etag=response["ETag"].strip('"'),
        )

    async def delete(self, *, tenant_id: str, key: str) -> None:
        object_key = self._object_key(tenant_id, key)
        try:
            async with self._client() as client:
                # S3 delete_object идемпотентен — не падает на отсутствующем ключе.
                await client.delete_object(Bucket=self._bucket, Key=object_key)
        except ClientError as exc:
            raise BlobStoreUnavailable(
                f"S3 delete_object failed: {exc}"
            ) from exc

    async def head(
        self, *, tenant_id: str, key: str
    ) -> BlobMetadata | None:
        object_key = self._object_key(tenant_id, key)
        try:
            async with self._client() as client:
                response = await client.head_object(
                    Bucket=self._bucket, Key=object_key
                )
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code")
            if code in ("404", "NoSuchKey", "NotFound"):
                return None
            raise BlobStoreUnavailable(
                f"S3 head_object failed: {exc}"
            ) from exc

        last_modified = response.get("LastModified")
        if last_modified and last_modified.tzinfo is None:
            last_modified = last_modified.replace(tzinfo=timezone.utc)

        return BlobMetadata(
            tenant_id=tenant_id,
            key=key,
            size=response["ContentLength"],
            etag=response["ETag"].strip('"'),
            last_modified=last_modified or datetime.now(timezone.utc),
            content_type=response.get("ContentType"),
            user_metadata=response.get("Metadata", {}),
        )

    async def list(
        self, *, tenant_id: str, prefix: str = ""
    ) -> AsyncIterator[BlobRef]:
        full_prefix = self._object_key(tenant_id, prefix) if prefix else (
            f"{tenant_id}{_TENANT_KEY_SEPARATOR}"
        )
        try:
            async with self._client() as client:
                paginator = client.get_paginator("list_objects_v2")
                async for page in paginator.paginate(
                    Bucket=self._bucket, Prefix=full_prefix
                ):
                    for obj in page.get("Contents", []):
                        rel_key = self._strip_tenant(tenant_id, obj["Key"])
                        yield BlobRef(
                            tenant_id=tenant_id,
                            key=rel_key,
                            etag=obj["ETag"].strip('"'),
                            size=obj["Size"],
                            content_type=None,  # требует HEAD для получения
                        )
        except ClientError as exc:
            raise BlobStoreUnavailable(
                f"S3 list_objects_v2 failed: {exc}"
            ) from exc

    async def presigned_url(
        self,
        *,
        tenant_id: str,
        key: str,
        op: PresignedOp,
        ttl_seconds: int = 3600,
        content_type: str | None = None,
    ) -> str:
        object_key = self._object_key(tenant_id, key)
        s3_op = {"GET": "get_object", "PUT": "put_object"}.get(op)
        if not s3_op:
            raise BlobStoreError(f"Unsupported presigned op: {op}")

        params: dict[str, Any] = {"Bucket": self._bucket, "Key": object_key}
        if op == "PUT" and content_type:
            params["ContentType"] = content_type

        try:
            async with self._client() as client:
                url = await client.generate_presigned_url(
                    s3_op, Params=params, ExpiresIn=ttl_seconds
                )
        except ClientError as exc:
            raise BlobStoreUnavailable(
                f"S3 generate_presigned_url failed: {exc}"
            ) from exc
        return str(url)
