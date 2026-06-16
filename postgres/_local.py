"""LocalAdapter — provisioning против локального/self-hosted PostgreSQL.

Использует ``asyncpg`` напрямую (не SQLAlchemy) для admin-операций:
``CREATE DATABASE`` / ``DROP DATABASE`` не выполняются внутри транзакции,
поэтому нужен autocommit-режим, который asyncpg даёт из коробки на уровне
отдельных команд.

Подключается к maintenance-БД (``postgres``) под admin-ролью, выполняет
control-plane операции, выдаёт DSN для per-tenant БД. PostGIS включается
для каждой созданной БД (а также предзагружается в ``template1`` через
init-скрипт compose — см. ``init/00-template-postgis.sql`` — это лишь
ускоряет старт, но не заменяет идемпотентный ``CREATE EXTENSION``).
"""
from __future__ import annotations

import asyncpg  # type: ignore[import-untyped]

from ._port import InvalidTenantError, PostgresPort, TenantId, database_name

__all__ = ["LocalAdapter"]


class LocalAdapter:
    """Control-plane адаптер для локального PostgreSQL + PostGIS.

    :param host: хост инстанса.
    :param port: порт инстанса (по умолчанию 5434 — basic-infra shifted,
        telcoss держит 5433; см. ADR-0013 §Coexistence).
    :param admin_user: admin-роль с правом ``CREATEDB``.
    :param admin_password: пароль admin-роли.
    :param allow_destructive: если False, :meth:`deprovision` бросает
        ``PermissionError``. Защита от случайного дропа в проде.
    """

    def __init__(
        self,
        *,
        host: str,
        port: int,
        admin_user: str,
        admin_password: str,
        allow_destructive: bool = False,
    ) -> None:
        self._host = host
        self._port = port
        self._admin_user = admin_user
        self._admin_password = admin_password
        self._allow_destructive = allow_destructive

    async def _admin_connect(self) -> asyncpg.Connection:
        """Соединение с maintenance-БД ``postgres`` под admin-ролью."""
        return await asyncpg.connect(
            host=self._host,
            port=self._port,
            user=self._admin_user,
            password=self._admin_password,
            database="postgres",
        )

    async def provision(self, tenant: TenantId) -> None:
        db = database_name(tenant)
        conn = await self._admin_connect()
        try:
            already = await conn.fetchval(
                "SELECT 1 FROM pg_database WHERE datname = $1", db
            )
            if not already:
                # Идентификатор уже провалидирован database_name(); кавычим
                # для защиты, значения через параметры здесь невозможны для DDL.
                await conn.execute(f'CREATE DATABASE "{db}"')
        finally:
            await conn.close()

        # PostGIS включается в контексте самой целевой БД.
        target = await asyncpg.connect(
            host=self._host,
            port=self._port,
            user=self._admin_user,
            password=self._admin_password,
            database=db,
        )
        try:
            await target.execute("CREATE EXTENSION IF NOT EXISTS postgis")
        finally:
            await target.close()

    async def deprovision(self, tenant: TenantId) -> None:
        if not self._allow_destructive:
            raise PermissionError(
                "deprovision запрещён: LocalAdapter создан с "
                "allow_destructive=False"
            )
        db = database_name(tenant)
        conn = await self._admin_connect()
        try:
            # FORCE завершает активные соединения (PostgreSQL 13+).
            await conn.execute(f'DROP DATABASE IF EXISTS "{db}" WITH (FORCE)')
        finally:
            await conn.close()

    async def exists(self, tenant: TenantId) -> bool:
        db = database_name(tenant)
        conn = await self._admin_connect()
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
        return (
            f"postgresql+{driver}://{self._admin_user}:{self._admin_password}"
            f"@{self._host}:{self._port}/{db}"
        )

    async def health(self) -> bool:
        try:
            conn = await self._admin_connect()
        except (OSError, asyncpg.PostgresError):
            return False
        try:
            return bool(await conn.fetchval("SELECT 1") == 1)
        finally:
            await conn.close()


# Проверка соответствия протоколу на этапе импорта (mypy + runtime).
_: PostgresPort = LocalAdapter(
    host="localhost", port=5434, admin_user="x", admin_password="x"
)
del _
