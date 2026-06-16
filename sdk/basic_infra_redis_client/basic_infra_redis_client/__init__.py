"""basic_infra_redis_client — data-plane SDK for the shared Redis layer (ADR-0014).

Tenant isolation = ACL user + key-prefix namespace on a single Redis (db 0).
"""

from .client import create_async_client, create_sync_client
from .config import RedisSettings, get_settings
from .health import check_health
from .namespace import RedisNamespace, derive_namespace, derive_username

__all__ = [
    "RedisSettings",
    "get_settings",
    "create_async_client",
    "create_sync_client",
    "check_health",
    "RedisNamespace",
    "derive_namespace",
    "derive_username",
]
