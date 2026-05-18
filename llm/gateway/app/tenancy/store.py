"""Tenant store — SQLite-backed CRUD for tenant records.

Per ADR-0003: tenants are projects in the author's ecosystem. Schema is small
enough that SQLite is overkill but consistent with the rest of the platform.

Schema (sketch — finalize in Phase 3):

    CREATE TABLE tenants (
        id              TEXT    PRIMARY KEY,
        api_key_hash    TEXT    NOT NULL,           -- bcrypt or argon2
        display_name    TEXT    NOT NULL,
        allowed_models  TEXT    NOT NULL,           -- JSON array; '["*"]' for all
        rate_limits     TEXT    NOT NULL DEFAULT '{}',  -- JSON object
        created_at      TEXT    NOT NULL,
        updated_at      TEXT    NOT NULL,
        deleted_at      TEXT
    );

    CREATE TABLE api_key_grace (
        tenant_id       TEXT    NOT NULL,
        old_api_key_hash TEXT   NOT NULL,
        expires_at      TEXT    NOT NULL,           -- 24h after rotation
        PRIMARY KEY (tenant_id, old_api_key_hash)
    );
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True)
class TenantRecord:
    id: str
    display_name: str
    allowed_models: tuple[str, ...]          # ("*",) for all
    rate_limits: dict[str, str] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    deleted_at: datetime | None = None


class TenantStore:
    """SQLite-backed tenant CRUD.

    Thread-safe (relies on sqlite3.connect with check_same_thread=False
    and a process-wide RLock for writes — writes are infrequent).
    """

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        # TODO(week4-phase-3): open sqlite3 connection, create schema if not exists

    def create(
        self,
        *,
        id: str,
        display_name: str,
        allowed_models: tuple[str, ...] = ("*",),
        rate_limits: dict[str, str] | None = None,
    ) -> tuple[TenantRecord, str]:
        """Create a tenant. Returns (record, raw_api_key).

        The raw api_key is returned ONCE, never stored. Only its hash is persisted.
        """
        raise NotImplementedError("week4-phase-3")

    def authenticate(self, raw_api_key: str) -> TenantRecord | None:
        """Look up tenant by raw api_key. Returns None if not found.

        Checks both the active key and the 24h grace window for rotated keys.
        """
        raise NotImplementedError("week4-phase-3")

    def rotate_key(self, tenant_id: str) -> str:
        """Generate new api_key, mark old in grace window for 24h. Returns raw key."""
        raise NotImplementedError("week4-phase-3")

    def get(self, tenant_id: str) -> TenantRecord | None:
        raise NotImplementedError("week4-phase-3")

    def list(self, include_deleted: bool = False) -> list[TenantRecord]:
        raise NotImplementedError("week4-phase-3")

    def soft_delete(self, tenant_id: str) -> None:
        raise NotImplementedError("week4-phase-3")
