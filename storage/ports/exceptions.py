"""Исключения порта хранилища блобов.

Иерархия:

    BlobStoreError
    ├── BlobNotFound          — запрошенный ключ не существует
    ├── BlobAlreadyExists     — попытка PUT с if-none-match для существующего ключа
    ├── TenantIsolationError  — попытка обращения к чужому tenant (sanity check)
    ├── BlobStoreUnavailable  — backend недоступен (network, auth, ...)
    └── BlobStoreConfigError  — ошибка конфигурации (отсутствует bucket, ...)
"""

from __future__ import annotations


class BlobStoreError(Exception):
    """Базовое исключение хранилища блобов."""


class BlobNotFound(BlobStoreError):
    """Запрошенный ключ отсутствует в хранилище."""

    def __init__(self, tenant_id: str, key: str) -> None:
        self.tenant_id = tenant_id
        self.key = key
        super().__init__(f"Blob not found: tenant={tenant_id!r} key={key!r}")


class BlobAlreadyExists(BlobStoreError):
    """Попытка PUT при существующем ключе с защитой от перезаписи."""

    def __init__(self, tenant_id: str, key: str) -> None:
        self.tenant_id = tenant_id
        self.key = key
        super().__init__(
            f"Blob already exists: tenant={tenant_id!r} key={key!r}"
        )


class TenantIsolationError(BlobStoreError):
    """Нарушение изоляции тенантов.

    Поднимается, если ключ или путь после конструирования адаптером
    выходит за границу префикса тенанта. Sanity check на случай багов
    в коде формирования ключей.
    """


class BlobStoreUnavailable(BlobStoreError):
    """Backend недоступен (сеть, авторизация, превышение лимитов)."""


class BlobStoreConfigError(BlobStoreError):
    """Ошибка конфигурации хранилища (нет bucket, неверный endpoint)."""
