"""Фабрики SQLAlchemy engine для tenant-БД (async + sync).

Async — ``asyncpg``; sync — ``psycopg`` (psycopg3). Engine кэшируется по
DSN-ключу в пределах процесса, чтобы повторные ``get_engine`` не плодили
пулы. Client project обычно вызывает ``get_async_engine`` один раз на
старте сервиса.
"""
from __future__ import annotations

from sqlalchemy import URL, create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from .config import PostgresSettings

__all__ = ["build_url", "get_async_engine", "get_sync_engine"]


def build_url(settings: PostgresSettings, *, driver: str) -> URL:
    """Собрать SQLAlchemy ``URL`` из настроек.

    :param driver: ``asyncpg`` (async) или ``psycopg`` (sync).
    """
    if driver not in ("asyncpg", "psycopg"):
        raise ValueError(f"неизвестный driver {driver!r}")
    query: dict[str, str] = {}
    if settings.sslmode:
        query["sslmode"] = settings.sslmode
    assert settings.database is not None  # выставлен валидатором config
    return URL.create(
        drivername=f"postgresql+{driver}",
        username=settings.user,
        password=settings.password,
        host=settings.host,
        port=settings.port,
        database=settings.database,
        query=query,
    )


def _pool_kwargs(settings: PostgresSettings) -> dict[str, object]:
    return {
        "pool_size": settings.pool_size,
        "max_overflow": settings.max_overflow,
        "pool_timeout": settings.pool_timeout,
        "pool_recycle": settings.pool_recycle,
        "pool_pre_ping": True,
        "echo": settings.echo,
    }


# Кэш по строковому ключу URL (включает driver, host, port, db, sslmode).
_async_cache: dict[str, AsyncEngine] = {}
_sync_cache: dict[str, Engine] = {}


def get_async_engine(settings: PostgresSettings) -> AsyncEngine:
    """Вернуть (создав при первом обращении) async engine для tenant-БД."""
    url = build_url(settings, driver="asyncpg")
    key = url.render_as_string(hide_password=False)
    engine = _async_cache.get(key)
    if engine is None:
        engine = create_async_engine(url, **_pool_kwargs(settings))
        _async_cache[key] = engine
    return engine


def get_sync_engine(settings: PostgresSettings) -> Engine:
    """Вернуть (создав при первом обращении) sync engine для tenant-БД."""
    url = build_url(settings, driver="psycopg")
    key = url.render_as_string(hide_password=False)
    engine = _sync_cache.get(key)
    if engine is None:
        engine = create_engine(url, **_pool_kwargs(settings))
        _sync_cache[key] = engine
    return engine
