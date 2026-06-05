"""LocalAdapter — real ACL provisioning against a self-hosted shared Redis."""

from __future__ import annotations

import secrets
from typing import Any, Optional

from basic_infra_redis_client.namespace import derive_namespace, derive_username

from .config import AdminSettings, get_admin_settings
from .port import TenantCredentials


class LocalAdapter:
    """Provisions tenant ACL users via an admin connection.

    Each tenant gets `app_<namespace>` limited to its key/channel prefix with
    dangerous commands removed (no FLUSHALL/CONFIG/etc.).
    """

    def __init__(self, settings: Optional[AdminSettings] = None) -> None:
        self._settings = settings or get_admin_settings()

    def _admin(self) -> Any:
        from redis.asyncio import Redis  # lazy

        kwargs: dict[str, Any] = {
            "host": self._settings.host,
            "port": self._settings.port,
            "username": self._settings.username,
            "decode_responses": True,
        }
        if self._settings.password:
            kwargs["password"] = self._settings.password
        if self._settings.ssl:
            kwargs["ssl"] = True
        return Redis(**kwargs)

    async def provision(self, tenant: str) -> TenantCredentials:
        namespace = derive_namespace(tenant)
        username = derive_username(tenant)
        password = secrets.token_urlsafe(24)

        admin = self._admin()
        try:
            # on, set password, reset then scope keys+channels, allow all but
            # the dangerous category. resetchannels clears the permissive default.
            await admin.execute_command(
                "ACL", "SETUSER", username,
                "on", f">{password}",
                "resetkeys", f"~{namespace}:*",
                "resetchannels", f"&{namespace}:*",
                "+@all", "-@dangerous",
            )
            if self._settings.acl_save:
                await admin.execute_command("ACL", "SAVE")
        finally:
            await admin.aclose()

        scheme = "rediss" if self._settings.ssl else "redis"
        dsn = (
            f"{scheme}://{username}:{password}@"
            f"{self._settings.host}:{self._settings.port}/0"
        )
        return TenantCredentials(
            tenant=tenant,
            username=username,
            password=password,
            namespace=namespace,
            dsn=dsn,
        )

    async def deprovision(self, tenant: str, *, purge: bool = False) -> None:
        username = derive_username(tenant)
        namespace = derive_namespace(tenant)
        admin = self._admin()
        try:
            await admin.execute_command("ACL", "DELUSER", username)
            if purge:
                # delete only the tenant's namespace keys, in batches via SCAN.
                cursor = 0
                while True:
                    cursor, keys = await admin.scan(
                        cursor=cursor, match=f"{namespace}:*", count=500
                    )
                    if keys:
                        await admin.delete(*keys)
                    if cursor == 0:
                        break
            if self._settings.acl_save:
                await admin.execute_command("ACL", "SAVE")
        finally:
            await admin.aclose()

    async def health(self) -> bool:
        admin = self._admin()
        try:
            return bool(await admin.ping())
        except Exception:
            return False
        finally:
            await admin.aclose()
