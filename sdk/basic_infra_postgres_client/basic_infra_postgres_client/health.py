"""Health-проверки tenant-БД для client projects.

Лёгкий ``SELECT 1`` + опциональная проверка наличия PostGIS. Предназначено
для readiness-проб (``/health/ready`` сервиса) и smoke-тестов.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from .config import PostgresSettings
from .engine import get_async_engine

__all__ = ["HealthResult", "check_health"]


@dataclass(frozen=True, slots=True)
class HealthResult:
    """Итог health-проверки tenant-БД.

    :ivar ok: общий статус (reachable И, если запрошено, PostGIS на месте).
    :ivar reachable: удалось выполнить ``SELECT 1``.
    :ivar postgis: версия PostGIS, либо None (не проверяли / отсутствует).
    :ivar detail: текст ошибки при недоступности.
    """

    ok: bool
    reachable: bool
    postgis: str | None
    detail: str | None = None


async def check_health(
    settings: PostgresSettings,
    *,
    require_postgis: bool = True,
) -> HealthResult:
    """Проверить доступность tenant-БД и (опц.) наличие PostGIS."""
    engine: AsyncEngine = get_async_engine(settings)
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
            postgis: str | None = None
            if require_postgis:
                row = await conn.execute(text("SELECT extversion FROM pg_extension WHERE extname = 'postgis'"))
                value = row.scalar_one_or_none()
                postgis = str(value) if value is not None else None
    except Exception as exc:  # noqa: BLE001 — health не должен пробрасывать
        return HealthResult(ok=False, reachable=False, postgis=None, detail=str(exc))

    ok = True if not require_postgis else postgis is not None
    detail = None if ok else "PostGIS не установлен в tenant-БД"
    return HealthResult(ok=ok, reachable=True, postgis=postgis, detail=detail)
