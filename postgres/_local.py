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
        app_password: str | None = None,
    ) -> None:
        self._host = host
        self._port = port
        self._admin_user = admin_user
        self._admin_password = admin_password
        self._allow_destructive = allow_destructive
        # Secret for the least-privilege runtime role ``app_<tenant>`` (ADR-0016
        # §2). When set, :meth:`provision` (re-)asserts the role; when absent,
        # role provisioning is skipped (back-compat: DB-only provisioning).
        self._app_password = app_password

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

        # Least-privilege runtime role (ADR-0016 §2) — only when the secret is
        # supplied; otherwise stay DB-only (back-compat).
        if self._app_password:
            await self.grant_runtime_role(tenant, self._app_password)

    async def grant_runtime_role(self, tenant: TenantId, password: str) -> None:
        """Idempotently (re-)assert the least-privilege runtime role ``app_<tenant>``.

        Runs as the admin/owner on the tenant DB. Creates the role if absent,
        then **always** re-asserts its attributes + password; grant-syncs
        runtime DML on every user schema; grants a narrow PostGIS set in
        ``public`` (no blanket ``SELECT``, nothing on ``alembic_version``); and
        sets database-wide ``DEFAULT PRIVILEGES`` for the owner so future
        migration-created tables/sequences are covered without re-running.

        Fully re-runnable: ``GRANT`` / ``ALTER DEFAULT PRIVILEGES`` are
        idempotent and ``CREATE ROLE`` is guarded. Schema-level ``USAGE`` for a
        *newly created* schema is picked up by re-running this after migrations
        (H4 runbook) — ``ALTER DEFAULT PRIVILEGES`` has no schema-level form.

        :raises ValueError: if ``password`` is empty (no weak default).
        """
        if not password:
            raise ValueError("grant_runtime_role: пустой пароль для runtime-роли")
        db = database_name(tenant)  # валидирует tenant → безопасный идентификатор
        role = f"app_{tenant}"
        owner = self._admin_user  # роль-владелец = тот, кто прогоняет миграции
        conn = await asyncpg.connect(
            host=self._host,
            port=self._port,
            user=self._admin_user,
            password=self._admin_password,
            database=db,
        )
        try:
            # Один транзакционный блок: гранты атомарны, а пароль живёт только в
            # transaction-local GUC (is_local=true), который сбрасывается на commit.
            async with conn.transaction():
                # Пароль уходит настоящим bind-параметром в set_config (не в текст
                # statement), затем читается server-side через current_setting и
                # квотируется format(%L) — без ручного экранирования и без
                # зависимости от standard_conforming_strings.
                await conn.execute(
                    "SELECT set_config('telcoss.app_pw', $1, true)", password
                )
                # Роль: создать при отсутствии, затем ВСЕГДА переутвердить атрибуты
                # + пароль (server-side %I/%L). role валидирован (app_<tenant>).
                await conn.execute(
                    "DO $$ BEGIN "
                    f"IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{role}') "
                    f'THEN CREATE ROLE "{role}"; END IF; '
                    "EXECUTE format("
                    "'ALTER ROLE %I WITH LOGIN NOSUPERUSER NOCREATEDB "
                    "NOCREATEROLE NOBYPASSRLS PASSWORD %L', "
                    f"'{role}', current_setting('telcoss.app_pw')); "
                    "END $$"
                )
            # Транзакция закрыта — пароль-GUC сброшен. Остальные гранты идемпотентны
            # и идут в autocommit.
            await conn.execute(f'GRANT CONNECT ON DATABASE "{db}" TO "{role}"')

            # grant-sync: runtime DML по всем user-схемам (кроме системных + public).
            schemas = await conn.fetch(
                "SELECT nspname FROM pg_namespace "
                "WHERE nspname NOT IN "
                "('pg_catalog', 'information_schema', 'pg_toast', 'public') "
                "AND nspname NOT LIKE 'pg_temp_%' "
                "AND nspname NOT LIKE 'pg_toast_temp_%'"
            )
            for record in schemas:
                s = str(record["nspname"]).replace('"', '""')
                await conn.execute(f'GRANT USAGE ON SCHEMA "{s}" TO "{role}"')
                await conn.execute(
                    f"GRANT SELECT, INSERT, UPDATE, DELETE "
                    f'ON ALL TABLES IN SCHEMA "{s}" TO "{role}"'
                )
                await conn.execute(
                    f'GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA "{s}" TO "{role}"'
                )

            # public: узкий PostGIS-набор (без blanket SELECT, без alembic_version).
            await conn.execute(f'GRANT USAGE ON SCHEMA public TO "{role}"')
            await conn.execute(
                f'GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO "{role}"'
            )
            postgis_rels = await conn.fetch(
                "SELECT c.relname FROM pg_class c "
                "JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = 'public' AND c.relname IN "
                "('spatial_ref_sys', 'geometry_columns', 'geography_columns')"
            )
            for record in postgis_rels:
                rel = str(record["relname"]).replace('"', '""')
                await conn.execute(f'GRANT SELECT ON public."{rel}" TO "{role}"')

            # future-proofing: объекты, создаваемые owner'ом позже (миграции),
            # database-wide (без IN SCHEMA) → покрывает таблицы в будущих схемах.
            await conn.execute(
                f'ALTER DEFAULT PRIVILEGES FOR ROLE "{owner}" '
                f'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO "{role}"'
            )
            await conn.execute(
                f'ALTER DEFAULT PRIVILEGES FOR ROLE "{owner}" '
                f'GRANT USAGE, SELECT ON SEQUENCES TO "{role}"'
            )
        finally:
            await conn.close()

    async def provision_outbox_reader(self, password: str) -> None:
        """Idempotently (re-)assert the least-privilege ``outbox_reader`` login role.

        Creates the role if absent, then always re-asserts LOGIN + password.
        No grants issued here — column-level grants on ``inventory.outbox`` are
        applied by telcoss migrations 0015/0017 (ADR-0019 §cross-repo coupling).

        :raises ValueError: if ``password`` is empty.
        """
        if not password:
            raise ValueError("provision_outbox_reader: пустой пароль")
        conn = await asyncpg.connect(
            host=self._host,
            port=self._port,
            user=self._admin_user,
            password=self._admin_password,
            database="postgres",
        )
        try:
            async with conn.transaction():
                await conn.execute(
                    "SELECT set_config('basic_infra.outbox_reader_pw', $1, true)",
                    password,
                )
                await conn.execute(
                    "DO $$ BEGIN "
                    "IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'outbox_reader') "
                    "THEN CREATE ROLE outbox_reader; END IF; "
                    "EXECUTE format("
                    "'ALTER ROLE outbox_reader WITH LOGIN NOSUPERUSER NOCREATEDB "
                    "NOCREATEROLE NOBYPASSRLS PASSWORD %L', "
                    "current_setting('basic_infra.outbox_reader_pw')); "
                    "END $$"
                )
        finally:
            await conn.close()

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
