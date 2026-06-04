"""Session-фабрики и контекст-менеджеры (async + sync).

Client project получает ``async_session_factory(settings)`` один раз на
старте и далее использует ``async with session_scope(factory) as s:`` для
транзакционных границ (commit при выходе, rollback при исключении).
"""
from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
)
from sqlalchemy.orm import Session, sessionmaker

from .config import PostgresSettings
from .engine import get_async_engine, get_sync_engine

__all__ = [
    "async_session_factory",
    "sync_session_factory",
    "session_scope",
    "sync_session_scope",
]


def async_session_factory(
    settings: PostgresSettings,
) -> async_sessionmaker[AsyncSession]:
    """Async sessionmaker, привязанный к engine tenant-БД."""
    engine = get_async_engine(settings)
    return async_sessionmaker(
        bind=engine, expire_on_commit=False, class_=AsyncSession
    )


def sync_session_factory(settings: PostgresSettings) -> sessionmaker[Session]:
    """Sync sessionmaker, привязанный к engine tenant-БД."""
    engine = get_sync_engine(settings)
    return sessionmaker(bind=engine, expire_on_commit=False, class_=Session)


@asynccontextmanager
async def session_scope(
    factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    """Транзакционная область: commit при успехе, rollback при ошибке."""
    session = factory()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


@contextmanager
def sync_session_scope(
    factory: sessionmaker[Session],
) -> Iterator[Session]:
    """Sync-вариант :func:`session_scope`."""
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
