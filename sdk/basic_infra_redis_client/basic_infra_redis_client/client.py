"""Redis client factories (data plane), async + sync.

Both build a connection pool from RedisSettings and return a client already
authenticated as the tenant's ACL user. Keys must be namespaced via
RedisSettings.namespacer() — the ACL pattern enforces it server-side regardless.
"""

from __future__ import annotations

from typing import Any, Optional

from .config import RedisSettings, get_settings


def _common_kwargs(settings: RedisSettings) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "host": settings.host,
        "port": settings.port,
        "db": settings.db,
        "max_connections": settings.max_connections,
        "decode_responses": True,
    }
    if settings.username:
        kwargs["username"] = settings.username
    if settings.password:
        kwargs["password"] = settings.password
    if settings.ssl:
        kwargs["ssl"] = True
    return kwargs


def create_async_client(settings: Optional[RedisSettings] = None) -> Any:
    """Return a redis.asyncio.Redis bound to the tenant's pool."""
    settings = settings or get_settings()
    from redis.asyncio import Redis  # lazy: SDK importable without redis present

    return Redis(**_common_kwargs(settings))


def create_sync_client(settings: Optional[RedisSettings] = None) -> Any:
    """Return a synchronous redis.Redis bound to the tenant's pool."""
    settings = settings or get_settings()
    from redis import Redis

    return Redis(**_common_kwargs(settings))
