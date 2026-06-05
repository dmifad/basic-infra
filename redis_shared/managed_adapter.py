"""ManagedAdapter — stub provisioning for a managed Redis (e.g. ElastiCache).

On managed targets ACL users are usually created out-of-band (IaC/console), so
provision/deprovision are stubs that raise; health and dsn still work so the
data plane can run against a managed instance. Mirrors postgres-multi's
ManagedAdapter (stub provision, working dsn/health) — wired when a cloud target
appears (deferred, see ADR-0014).
"""

from __future__ import annotations

from typing import Any, Optional

from .config import AdminSettings, get_admin_settings
from .port import TenantCredentials


class ManagedAdapter:
    def __init__(self, settings: Optional[AdminSettings] = None) -> None:
        self._settings = settings or get_admin_settings()

    async def provision(self, tenant: str) -> TenantCredentials:
        raise NotImplementedError(
            "ManagedAdapter.provision is a stub — create the ACL user via the "
            "managed provider's IaC/console (ADR-0014)."
        )

    async def deprovision(self, tenant: str, *, purge: bool = False) -> None:
        raise NotImplementedError(
            "ManagedAdapter.deprovision is a stub — remove the ACL user via the "
            "managed provider's IaC/console (ADR-0014)."
        )

    def _admin(self) -> Any:
        from redis.asyncio import Redis

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

    async def health(self) -> bool:
        admin = self._admin()
        try:
            return bool(await admin.ping())
        except Exception:
            return False
        finally:
            await admin.aclose()
