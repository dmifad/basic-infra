"""Tenant -> Redis key-namespace derivation (data plane).

Shared Redis isolates client projects by ACL user + key-prefix namespace on a
single instance (db 0), NOT by db number (Redis discourages SELECT-based
multi-db and ACLs are weak per-db). The control plane (redis/) provisions an
ACL user `app_<tenant>` restricted to `~<namespace>:*`; this module derives the
matching namespace and prefixes keys so the SDK never writes outside it.
"""

from __future__ import annotations

import re

_SANITIZE = re.compile(r"[^a-z0-9_]+")


def derive_namespace(tenant: str) -> str:
    """`my-tenant` -> `my_tenant`. Lowercase, hyphen->underscore, strip junk.

    Mirrors the postgres-multi hyphen->underscore tenant->db rule so a tenant
    string maps consistently across platform layers.
    """
    norm = _SANITIZE.sub("_", tenant.strip().lower()).strip("_")
    if not norm:
        raise ValueError(f"tenant {tenant!r} normalises to an empty namespace")
    return norm


def derive_username(tenant: str) -> str:
    """ACL username for a tenant: `app_<namespace>`."""
    return f"app_{derive_namespace(tenant)}"


class RedisNamespace:
    """Prefixes keys with `<namespace>:` so callers cannot escape the tenant.

    Use `ns.key("session:42")` -> `"<namespace>:session:42"`. The ACL pattern
    `~<namespace>:*` enforces this server-side even if a caller forgets.
    """

    __slots__ = ("namespace",)

    def __init__(self, namespace: str) -> None:
        self.namespace = namespace

    def key(self, name: str) -> str:
        return f"{self.namespace}:{name}"

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return f"RedisNamespace({self.namespace!r})"
