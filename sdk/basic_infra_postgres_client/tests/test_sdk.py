"""Тесты postgres-multi: unit (всегда) + integration (маркер ``integration``).

Unit-тесты не требуют БД: проверяют валидацию tenant, вывод имени БД,
сборку URL, дефолты config, protocol conformance адаптеров.

Integration-тесты поднимают реальный PostGIS-контейнер через
testcontainers и гоняют полный цикл: provision → connect через SDK →
round-trip запрос → проверка PostGIS → deprovision. Помечены
``@pytest.mark.integration`` и исключены из ``make test`` (deselect),
запускаются ``make test-integration``.
"""
from __future__ import annotations

import os

import pytest

from basic_infra_postgres_client import (
    PostgresSettings,
    build_url,
)


# ─────────────────────────── unit: control plane ───────────────────────────


def test_database_name_simple() -> None:
    from postgres import TenantId, database_name

    assert database_name(TenantId("telcoss")) == "telcoss"


def test_database_name_hyphen_to_underscore() -> None:
    from postgres import TenantId, database_name

    assert database_name(TenantId("pamyat-naroda-graph")) == "pamyat_naroda_graph"


@pytest.mark.parametrize(
    "bad",
    ["", "1abc", "-abc", "abc-", "ABC", "a b", "a;b", "x" * 65],
)
def test_database_name_rejects_invalid(bad: str) -> None:
    from postgres import InvalidTenantError, TenantId, database_name

    with pytest.raises(InvalidTenantError):
        database_name(TenantId(bad))


def test_adapters_satisfy_protocol() -> None:
    from postgres import LocalAdapter, ManagedAdapter, PostgresPort

    local = LocalAdapter(
        host="h", port=5434, admin_user="u", admin_password="p"
    )
    managed = ManagedAdapter(host="h", port=5432, user="u", password="p")
    assert isinstance(local, PostgresPort)
    assert isinstance(managed, PostgresPort)


@pytest.mark.asyncio
async def test_managed_provision_is_stub() -> None:
    from postgres import ManagedAdapter, TenantId

    adapter = ManagedAdapter(host="h", port=5432, user="u", password="p")
    with pytest.raises(NotImplementedError):
        await adapter.provision(TenantId("telcoss"))


@pytest.mark.asyncio
async def test_local_deprovision_guarded() -> None:
    from postgres import LocalAdapter, TenantId

    adapter = LocalAdapter(
        host="h", port=5434, admin_user="u", admin_password="p"
    )  # allow_destructive=False по умолчанию
    with pytest.raises(PermissionError):
        await adapter.deprovision(TenantId("telcoss"))


# ─────────────────────────────── unit: SDK ─────────────────────────────────


def _settings(**over: object) -> PostgresSettings:
    base: dict[str, object] = {
        "tenant": "telcoss",
        "user": "app",
        "password": "secret",
    }
    base.update(over)
    return PostgresSettings(**base)  # type: ignore[arg-type]


def test_database_defaults_from_tenant() -> None:
    assert _settings(tenant="pamyat-naroda-graph").database == "pamyat_naroda_graph"


def test_explicit_database_overrides_tenant() -> None:
    assert _settings(database="custom_db").database == "custom_db"


def test_managed_forces_sslmode() -> None:
    s = _settings(provider="managed")
    assert s.sslmode == "require"


def test_local_no_sslmode_by_default() -> None:
    assert _settings(provider="local").sslmode is None


def test_build_url_async() -> None:
    url = build_url(_settings(), driver="asyncpg")
    assert url.drivername == "postgresql+asyncpg"
    assert url.database == "telcoss"
    assert url.host == "localhost"
    assert url.port == 5434


def test_build_url_sync() -> None:
    url = build_url(_settings(), driver="psycopg")
    assert url.drivername == "postgresql+psycopg"


def test_build_url_rejects_bad_driver() -> None:
    with pytest.raises(ValueError):
        build_url(_settings(), driver="pg8000")


def test_build_url_includes_sslmode_for_managed() -> None:
    url = build_url(_settings(provider="managed"), driver="asyncpg")
    assert url.query.get("sslmode") == "require"


def test_settings_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BASIC_INFRA_POSTGRES_TENANT", "telcoss")
    monkeypatch.setenv("BASIC_INFRA_POSTGRES_USER", "app")
    monkeypatch.setenv("BASIC_INFRA_POSTGRES_PASSWORD", "secret")
    monkeypatch.setenv("BASIC_INFRA_POSTGRES_PORT", "5440")
    s = PostgresSettings()
    assert s.tenant == "telcoss"
    assert s.port == 5440
    assert s.database == "telcoss"


# ────────────────────────── integration (testcontainers) ───────────────────

POSTGIS_IMAGE = os.environ.get("POSTGIS_TEST_IMAGE", "postgis/postgis:16-3.4")


@pytest.fixture(scope="module")
def postgis_container():  # type: ignore[no-untyped-def]
    pytest.importorskip("testcontainers.postgres")
    from testcontainers.postgres import PostgresContainer

    with PostgresContainer(POSTGIS_IMAGE, username="postgres", password="postgres") as pg:
        yield pg


@pytest.mark.integration
@pytest.mark.asyncio
async def test_provision_connect_roundtrip(postgis_container) -> None:  # type: ignore[no-untyped-def]
    from sqlalchemy import text

    from basic_infra_postgres_client import (
        async_session_factory,
        check_health,
        session_scope,
    )
    from postgres import LocalAdapter, TenantId

    host = postgis_container.get_container_host_ip()
    port = int(postgis_container.get_exposed_port(5432))

    adapter = LocalAdapter(
        host=host,
        port=port,
        admin_user="postgres",
        admin_password="postgres",
        allow_destructive=True,
    )
    tenant = TenantId("telcoss")

    assert await adapter.health() is True
    assert await adapter.exists(tenant) is False
    await adapter.provision(tenant)
    assert await adapter.exists(tenant) is True
    # Идемпотентность.
    await adapter.provision(tenant)

    settings = PostgresSettings(
        tenant="telcoss",
        user="postgres",
        password="postgres",
        host=host,
        port=port,
    )

    health = await check_health(settings, require_postgis=True)
    assert health.ok is True
    assert health.postgis is not None

    factory = async_session_factory(settings)
    async with session_scope(factory) as session:
        value = (await session.execute(text("SELECT 42"))).scalar_one()
        assert value == 42

    await adapter.deprovision(tenant)
    assert await adapter.exists(tenant) is False


@pytest.mark.integration
@pytest.mark.asyncio
async def test_app_role_reassert_strips_drift_when_reprovisioned(postgis_container) -> None:  # type: ignore[no-untyped-def]
    """H2a consume-and-reassert: re-provisioning re-asserts the least-privilege
    role attributes, stripping any drift. Hermetic — throwaway PostGIS container,
    never the live shared instance (provision is a mutation)."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    from postgres import LocalAdapter, TenantId

    host = postgis_container.get_container_host_ip()
    port = int(postgis_container.get_exposed_port(5432))
    tenant = TenantId("telcoss")
    adapter = LocalAdapter(
        host=host,
        port=port,
        admin_user="postgres",
        admin_password="postgres",
        allow_destructive=True,
        app_password="t3st-app-secret",
    )

    # Idempotent: provisioning twice must not raise.
    await adapter.provision(tenant)
    await adapter.provision(tenant)

    admin = create_async_engine(
        f"postgresql+asyncpg://postgres:postgres@{host}:{port}/telcoss", echo=False
    )

    async def _attrs():  # type: ignore[no-untyped-def]
        async with admin.connect() as conn:
            return (await conn.execute(text(
                "SELECT rolsuper, rolcreatedb, rolcreaterole, rolbypassrls, rolcanlogin "
                "FROM pg_roles WHERE rolname = 'app_telcoss'"
            ))).one()

    try:
        row = await _attrs()
        assert (row.rolsuper, row.rolcreatedb, row.rolcreaterole, row.rolbypassrls) == (
            False, False, False, False,
        )
        assert row.rolcanlogin is True

        # Inject drift, confirm it took, then re-provision → reassert strips it.
        async with admin.begin() as conn:
            await conn.execute(text('ALTER ROLE "app_telcoss" CREATEDB SUPERUSER'))
        drifted = await _attrs()
        assert (drifted.rolsuper, drifted.rolcreatedb) == (True, True)

        await adapter.provision(tenant)  # consume-and-reassert
        fixed = await _attrs()
        assert (fixed.rolsuper, fixed.rolcreatedb) == (False, False)
    finally:
        await admin.dispose()
