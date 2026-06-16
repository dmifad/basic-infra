"""Health probe for the shared Redis layer."""

from __future__ import annotations

from typing import Any, Optional

from .client import create_async_client
from .config import RedisSettings


async def check_health(settings: Optional[RedisSettings] = None) -> bool:
    """PING the tenant connection. True on PONG, False on any failure.

    Closes the client it creates so probes don't leak connections.
    """
    client: Any = create_async_client(settings)
    try:
        return bool(await client.ping())
    except Exception:
        return False
    finally:
        await client.aclose()
