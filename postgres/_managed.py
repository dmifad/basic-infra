"""ManagedAdapter — cloud/managed PostgreSQL (RDS / Cloud SQL / Neon).

**Stub на Week 8** (ADR-0013 §Out of scope). В managed-окружениях БД
обычно provisioned вне приложения (Terraform / консоль провайдера), поэтому
control-plane методы ``provision`` / ``deprovision`` намеренно бросают
``NotImplementedError`` — их реализация откладывается до появления реального
cloud-таргета.

Что РАБОТАЕТ уже сейчас: ``dsn`` (резолвит per-tenant connection string из
шаблона) и ``health`` (пингует инстанс). Этого достаточно, чтобы client
project переключался ``local`` → ``managed`` через env без изменения кода,
как только облако появится.
"""
from __future__ import annotations

import asyncpg  # type: ignore[import-untyped]

from ._port import InvalidTenantError, PostgresPort, TenantId, database_name

__all__ = ["ManagedAdapter"]


class ManagedAdapter:
    """Адаптер для managed PostgreSQL.

    :param host: endpoint провайдера.
    :param port: порт (обычно 5432 у managed).
    :param user: роль приложения.
    :param password: пароль роли.
    :param sslmode: режим TLS (managed почти всегда требует ``require``).
    """

    def __init__(
        self,
        *,
        host: str,
        port: int,
        user: str,
        password: str,
        sslmode: str = "require",
    ) -> None:
        self._host = host
        self._port = port
        self._user = user
        self._password = password
        self._sslmode = sslmode

    async def provision(self, tenant: TenantId) -> None:
        raise NotImplementedError(
            "ManagedAdapter.provision — stub (Week 8). Managed-БД создаются "
            "вне приложения (Terraform/консоль). См. ADR-0013 §Out of scope."
        )

    async def deprovision(self, tenant: TenantId) -> None:
        raise NotImplementedError(
            "ManagedAdapter.deprovision — stub (Week 8). Удаление managed-БД "
            "выполняется через инструменты провайдера."
        )

    async def exists(self, tenant: TenantId) -> bool:
        db = database_name(tenant)
        try:
            conn = await asyncpg.connect(
                host=self._host,
                port=self._port,
                user=self._user,
                password=self._password,
                database="postgres",
                ssl=self._sslmode,
            )
        except (OSError, asyncpg.PostgresError):
            return False
        try:
            row = await conn.fetchval(
                "SELECT 1 FROM pg_database WHERE datname = $1", db
            )
            return row is not None
        finally:
            await conn.close()

    async def dsn(self, tenant: TenantId, *, driver: str = "asyncpg") -> str:
        db = database_name(tenant)
        if driver not in ("asyncpg", "psycopg"):
            raise InvalidTenantError(f"неизвестный driver {driver!r}")
        # ssl передаётся как query-параметр; asyncpg/psycopg оба понимают.
        return (
            f"postgresql+{driver}://{self._user}:{self._password}"
            f"@{self._host}:{self._port}/{db}?sslmode={self._sslmode}"
        )

    async def health(self) -> bool:
        try:
            conn = await asyncpg.connect(
                host=self._host,
                port=self._port,
                user=self._user,
                password=self._password,
                database="postgres",
                ssl=self._sslmode,
            )
        except (OSError, asyncpg.PostgresError):
            return False
        try:
            return bool(await conn.fetchval("SELECT 1") == 1)
        finally:
            await conn.close()


_: PostgresPort = ManagedAdapter(
    host="x", port=5432, user="x", password="x"
)
del _
