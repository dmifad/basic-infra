"""Control-plane port + types for shared Redis provisioning."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class TenantCredentials:
    """Result of provisioning a tenant on the shared Redis."""

    tenant: str
    username: str
    password: str
    namespace: str
    dsn: str


@runtime_checkable
class RedisProvisioningPort(Protocol):
    """Provision / deprovision tenant access on the shared Redis layer."""

    async def provision(self, tenant: str) -> TenantCredentials:
        """Create (or rotate) the tenant's ACL user. Idempotent on the user."""
        ...

    async def deprovision(self, tenant: str, *, purge: bool = False) -> None:
        """Remove the tenant's ACL user. If purge, also delete its namespace keys.

        Callers (CLI/Makefile) MUST gate this behind explicit confirmation.
        """
        ...

    async def health(self) -> bool:
        """True if the admin connection reaches the server."""
        ...
