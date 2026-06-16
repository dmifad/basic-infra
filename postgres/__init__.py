"""postgres-multi — control-plane слой basic-infra (ADR-0013).

Provisioning per-client-project баз данных (database-per-client-project).
Data plane (engine/session для client projects) — в SDK
``basic_infra_postgres_client``.
"""
from __future__ import annotations

from ._local import LocalAdapter
from ._managed import ManagedAdapter
from ._port import (
    InvalidTenantError,
    PostgresPort,
    TenantId,
    database_name,
)

__all__ = [
    "PostgresPort",
    "TenantId",
    "InvalidTenantError",
    "database_name",
    "LocalAdapter",
    "ManagedAdapter",
]
