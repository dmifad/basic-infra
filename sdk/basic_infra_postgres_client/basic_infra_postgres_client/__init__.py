"""basic_infra_postgres_client — data-plane SDK для tenant-БД.

Client project импортирует отсюда. Control plane (provisioning) — в пакете
``postgres`` платформы (ADR-0013).

Пример::

    from basic_infra_postgres_client import (
        PostgresSettings, async_session_factory, session_scope, check_health,
    )

    settings = PostgresSettings()              # из env BASIC_INFRA_POSTGRES_*
    factory = async_session_factory(settings)

    async with session_scope(factory) as session:
        result = await session.execute(...)     # доменные запросы проекта
"""
from __future__ import annotations

from .config import PostgresSettings
from .engine import build_url, get_async_engine, get_sync_engine
from .health import HealthResult, check_health
from .session import (
    async_session_factory,
    session_scope,
    sync_session_factory,
    sync_session_scope,
)

__all__ = [
    "PostgresSettings",
    "build_url",
    "get_async_engine",
    "get_sync_engine",
    "async_session_factory",
    "sync_session_factory",
    "session_scope",
    "sync_session_scope",
    "check_health",
    "HealthResult",
]
