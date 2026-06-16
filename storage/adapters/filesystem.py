"""Адаптер хранилища поверх локальной файловой системы.

Назначение — миграционный мост. Позволяет существующим потребителям
(pdf-intake пишет в /var/telcoss/pdf-intake/) принять `BlobStorePort`
без изменения поведения. После принятия можно переключить адаптер на
MinIO/S3 без правок прикладного кода.

Раскладка на диске:

    {filesystem_root}/{tenant_id}/{key}

где `tenant_id` и `key` нормализуются для защиты от path traversal.

ETag вычисляется как sha256 содержимого. Это дороже чем S3-овский
MD5, но даёт детерминированный contract-совместимый идентификатор
без зависимости от файловой системы.

Presigned URL не поддерживается — file:// не имеют TTL. Метод
поднимает BlobStoreError.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import AsyncIterator

import aiofiles
import aiofiles.os

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
    BlobStoreConfigError,
    BlobStoreError,
    TenantIsolationError,
)

# Размер чанка для стримингового чтения/записи.
_CHUNK_SIZE = 1024 * 1024  # 1 MiB

# Суффикс файла метаданных. Лежит рядом с блобом.
_META_SUFFIX = ".meta.json"


class _FilesystemBlobData(BlobData):
    """Реализация BlobData, читающая чанки из файла."""

    def __init__(self, path: Path, **kwargs: object) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self._path = path

    async def stream(self) -> AsyncIterator[bytes]:
        async with aiofiles.open(self._path, "rb") as f:
            while True:
                chunk = await f.read(_CHUNK_SIZE)
                if not chunk:
                    break
                yield chunk


class FilesystemAdapter(BlobStorePort):
    """Хранилище поверх локальной ФС.

    :param filesystem_root: корневая директория. Все блобы укладываются
        под неё. Не существующий путь — ошибка конфигурации.
    """

    def __init__(self, filesystem_root: str | Path) -> None:
        root = Path(filesystem_root).resolve()
        if not root.exists():
            raise BlobStoreConfigError(
                f"Filesystem root does not exist: {root}"
            )
        if not root.is_dir():
            raise BlobStoreConfigError(
                f"Filesystem root is not a directory: {root}"
            )
        self._root = root

    # --- Внутренние утилиты ----------------------------------------

    def _resolve(self, tenant_id: str, key: str) -> Path:
        """Сконструировать безопасный путь под root.

        Защита от path traversal: нормализуем компоненты и проверяем,
        что итоговый путь лежит под `self._root`.
        """
        if not tenant_id or "/" in tenant_id or tenant_id in (".", ".."):
            raise TenantIsolationError(
                f"Invalid tenant_id: {tenant_id!r}"
            )

        # Используем PurePosixPath для нормализации форвард-слешей в key.
        normalized_key = PurePosixPath(key)
        if normalized_key.is_absolute() or ".." in normalized_key.parts:
            raise TenantIsolationError(
                f"Invalid key (absolute or contains '..'): {key!r}"
            )

        candidate = (self._root / tenant_id / normalized_key).resolve()

        # Финальная проверка: candidate должен быть под root.
        try:
            candidate.relative_to(self._root)
        except ValueError as exc:
            raise TenantIsolationError(
                f"Resolved path escapes filesystem root: "
                f"tenant={tenant_id!r} key={key!r} resolved={candidate}"
            ) from exc

        return candidate

    def _meta_path(self, blob_path: Path) -> Path:
        return blob_path.with_name(blob_path.name + _META_SUFFIX)

    @staticmethod
    def _compute_etag(path: Path) -> str:
        h = hashlib.sha256()
        with path.open("rb") as f:
            while True:
                chunk = f.read(_CHUNK_SIZE)
                if not chunk:
                    break
                h.update(chunk)
        return h.hexdigest()

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
        path = self._resolve(tenant_id, key)

        if if_none_match and path.exists():
            raise BlobAlreadyExists(tenant_id=tenant_id, key=key)

        await aiofiles.os.makedirs(path.parent, exist_ok=True)

        # Пишем атомарно: сначала во временный файл, потом rename.
        tmp_path = path.with_name(path.name + ".tmp")
        h = hashlib.sha256()
        size = 0

        try:
            async with aiofiles.open(tmp_path, "wb") as f:
                if isinstance(data, bytes):
                    h.update(data)
                    size = len(data)
                    await f.write(data)
                else:
                    async for chunk in data:
                        h.update(chunk)
                        size += len(chunk)
                        await f.write(chunk)
            # Atomic move.
            os.replace(tmp_path, path)
        except Exception:
            # Cleanup при сбое.
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)
            raise

        etag = h.hexdigest()

        # Метаданные пишем рядом отдельным файлом.
        meta_payload = {
            "content_type": content_type,
            "user_metadata": metadata or {},
            "etag": etag,
            "size": size,
        }
        async with aiofiles.open(self._meta_path(path), "w") as f:
            await f.write(json.dumps(meta_payload, ensure_ascii=False))

        return BlobRef(
            tenant_id=tenant_id,
            key=key,
            etag=etag,
            size=size,
            content_type=content_type,
        )

    async def get(self, *, tenant_id: str, key: str) -> BlobData:
        path = self._resolve(tenant_id, key)
        if not path.exists():
            raise BlobNotFound(tenant_id=tenant_id, key=key)

        meta = await self._load_meta(path, tenant_id, key)
        return _FilesystemBlobData(
            path=path,
            tenant_id=tenant_id,
            key=key,
            size=meta.size,
            content_type=meta.content_type,
            etag=meta.etag,
        )

    async def delete(self, *, tenant_id: str, key: str) -> None:
        path = self._resolve(tenant_id, key)
        # Идемпотентно: missing_ok=True.
        await aiofiles.os.remove(path) if path.exists() else None
        meta_path = self._meta_path(path)
        if meta_path.exists():
            await aiofiles.os.remove(meta_path)

    async def head(
        self, *, tenant_id: str, key: str
    ) -> BlobMetadata | None:
        path = self._resolve(tenant_id, key)
        if not path.exists():
            return None
        return await self._load_meta(path, tenant_id, key)

    async def list(
        self, *, tenant_id: str, prefix: str = ""
    ) -> AsyncIterator[BlobRef]:
        # Sanity check на tenant_id; prefix может быть пустым.
        tenant_root = self._resolve(tenant_id, ".") if False else (
            self._root / tenant_id
        )
        if not tenant_root.exists():
            return

        # Защита от вложенного traversal в prefix.
        prefix_path = PurePosixPath(prefix) if prefix else None
        if prefix_path and (
            prefix_path.is_absolute() or ".." in prefix_path.parts
        ):
            raise TenantIsolationError(
                f"Invalid prefix: {prefix!r}"
            )

        for p in tenant_root.rglob("*"):
            if not p.is_file():
                continue
            if p.name.endswith(_META_SUFFIX):
                continue
            rel_key = str(p.relative_to(tenant_root)).replace(os.sep, "/")
            if prefix and not rel_key.startswith(prefix):
                continue
            meta = await self._load_meta(p, tenant_id, rel_key)
            yield BlobRef(
                tenant_id=tenant_id,
                key=rel_key,
                etag=meta.etag,
                size=meta.size,
                content_type=meta.content_type,
            )

    async def presigned_url(
        self,
        *,
        tenant_id: str,
        key: str,
        op: PresignedOp,
        ttl_seconds: int = 3600,
        content_type: str | None = None,
    ) -> str:
        raise BlobStoreError(
            "FilesystemAdapter does not support presigned URLs. "
            "Switch to MinioAdapter or S3Adapter for this functionality."
        )

    async def aclose(self) -> None:
        """No-op: у файловой ФС нет долгоживущего клиента для закрытия."""
        return None

    # --- Загрузка метаданных ---------------------------------------

    async def _load_meta(
        self, path: Path, tenant_id: str, key: str
    ) -> BlobMetadata:
        meta_path = self._meta_path(path)
        if meta_path.exists():
            async with aiofiles.open(meta_path, "r") as f:
                payload = json.loads(await f.read())
            return BlobMetadata(
                tenant_id=tenant_id,
                key=key,
                size=payload["size"],
                etag=payload["etag"],
                last_modified=datetime.fromtimestamp(
                    path.stat().st_mtime, tz=timezone.utc
                ),
                content_type=payload.get("content_type"),
                user_metadata=payload.get("user_metadata", {}),
            )

        # Файл существует без метаданных — это файлы, существовавшие до
        # adoption SDK. Реконструируем метаданные на лету (size, mtime,
        # вычисляем etag). Это путь, по которому идут все pdf-intake
        # файлы до завершения миграции.
        stat = path.stat()
        return BlobMetadata(
            tenant_id=tenant_id,
            key=key,
            size=stat.st_size,
            etag=self._compute_etag(path),
            last_modified=datetime.fromtimestamp(
                stat.st_mtime, tz=timezone.utc
            ),
            content_type=None,
            user_metadata={},
        )
