"""Tenant store — SQLite-backed CRUD for tenant records.

Per ADR-0003: a tenant is a project in the author's ecosystem. Write volume is
"one tenant per quarter", so SQLite is more than sufficient.

Tables::

    tenants(id PK, api_key_hash, display_name, allowed_models JSON,
            rate_limits JSON, created_at, updated_at, deleted_at)
    api_key_grace(tenant_id, old_api_key_hash, expires_at, PK(tenant_id, hash))

API keys are stored only as Argon2 hashes. The raw key is returned exactly once
by :meth:`TenantStore.create` / :meth:`TenantStore.rotate_key` and never again.
"""
from __future__ import annotations

import json
import secrets
import sqlite3
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

_KEY_PREFIX = "tnk_live_"
_DEFAULT_GRACE = timedelta(hours=24)
_hasher = PasswordHasher()

_SCHEMA = """
CREATE TABLE IF NOT EXISTS tenants (
    id              TEXT    PRIMARY KEY,
    api_key_hash    TEXT    NOT NULL,
    display_name    TEXT    NOT NULL,
    allowed_models  TEXT    NOT NULL DEFAULT '["*"]',
    rate_limits     TEXT    NOT NULL DEFAULT '{}',
    created_at      TEXT    NOT NULL,
    updated_at      TEXT    NOT NULL,
    deleted_at      TEXT
);
CREATE TABLE IF NOT EXISTS api_key_grace (
    tenant_id           TEXT    NOT NULL,
    old_api_key_hash    TEXT    NOT NULL,
    expires_at          TEXT    NOT NULL,
    PRIMARY KEY (tenant_id, old_api_key_hash)
);
"""


@dataclass(frozen=True)
class TenantRecord:
    """A tenant as seen by the rest of the gateway. Carries no secret material."""

    id: str
    display_name: str
    allowed_models: tuple[str, ...]
    rate_limits: dict[str, str] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    deleted_at: datetime | None = None


class TenantExists(Exception):
    """Raised by :meth:`TenantStore.create` when the id is already taken."""


class TenantNotFound(Exception):
    """Raised when an operation targets a tenant id that does not exist."""


def generate_api_key() -> str:
    """Return a fresh opaque API key: ``tnk_live_<43 url-safe chars>``."""
    return _KEY_PREFIX + secrets.token_urlsafe(32)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _parse_dt(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


class TenantStore:
    """SQLite-backed tenant CRUD.

    Thread-safe: a single shared connection (``check_same_thread=False``) guarded
    by a process-wide :class:`threading.RLock`. Writes are rare, so coarse
    locking is fine.
    """

    def __init__(self, db_path: Path | str, *, grace_period: timedelta = _DEFAULT_GRACE) -> None:
        """Open (creating if needed) the tenant database at ``db_path``.

        Args:
            db_path: filesystem path, or ``":memory:"`` for an ephemeral store.
            grace_period: how long a rotated key keeps working. Lower it in tests.
        """
        self.db_path = Path(db_path)
        self.grace_period = grace_period
        self._lock = threading.RLock()
        if str(db_path) != ":memory:":
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        with self._lock:
            self._conn.executescript(_SCHEMA)
            self._conn.commit()

    def close(self) -> None:
        """Close the underlying SQLite connection."""
        with self._lock:
            self._conn.close()

    # ─── reads ──────────────────────────────────────────────────────────────

    def get(self, tenant_id: str) -> TenantRecord | None:
        """Return the tenant by id, or ``None`` if absent (including soft-deleted)."""
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM tenants WHERE id = ?", (tenant_id,)
            ).fetchone()
        return _row_to_record(row) if row is not None else None

    def list(self, include_deleted: bool = False) -> list[TenantRecord]:
        """Return all tenants, oldest first. Soft-deleted ones are excluded by default."""
        sql = "SELECT * FROM tenants"
        if not include_deleted:
            sql += " WHERE deleted_at IS NULL"
        sql += " ORDER BY created_at"
        with self._lock:
            rows = self._conn.execute(sql).fetchall()
        return [_row_to_record(r) for r in rows]

    def authenticate(self, raw_api_key: str) -> TenantRecord | None:
        """Resolve a raw API key to its tenant.

        Checks each active tenant's current key, then any unexpired rotated key
        in the 24 h grace window. Returns ``None`` if nothing matches.
        Soft-deleted tenants never authenticate.
        """
        with self._lock:
            active = self._conn.execute(
                "SELECT * FROM tenants WHERE deleted_at IS NULL"
            ).fetchall()
        for row in active:
            if _verify(row["api_key_hash"], raw_api_key):
                return _row_to_record(row)

        now = datetime.now(UTC)
        with self._lock:
            grace = self._conn.execute("SELECT * FROM api_key_grace").fetchall()
        for row in grace:
            expires = _parse_dt(row["expires_at"])
            if expires is None or expires < now:
                continue
            if _verify(row["old_api_key_hash"], raw_api_key):
                return self.get(row["tenant_id"])
        return None

    # ─── writes ─────────────────────────────────────────────────────────────

    def create(
        self,
        *,
        id: str,
        display_name: str,
        allowed_models: tuple[str, ...] = ("*",),
        rate_limits: dict[str, str] | None = None,
    ) -> tuple[TenantRecord, str]:
        """Create a tenant and return ``(record, raw_api_key)``.

        The raw key is shown once here and never persisted — only its hash is.

        Raises:
            TenantExists: if ``id`` is already present.
        """
        if self.get(id) is not None:
            raise TenantExists(f"tenant already exists: {id}")
        raw_key = generate_api_key()
        now = _now_iso()
        with self._lock:
            self._conn.execute(
                "INSERT INTO tenants (id, api_key_hash, display_name, allowed_models,"
                " rate_limits, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    id,
                    _hasher.hash(raw_key),
                    display_name,
                    json.dumps(list(allowed_models)),
                    json.dumps(rate_limits or {}),
                    now,
                    now,
                ),
            )
            self._conn.commit()
        record = self.get(id)
        assert record is not None  # just inserted
        return record, raw_key

    def rotate_key(self, tenant_id: str) -> str:
        """Issue a new API key; the old one stays valid for the grace period.

        Returns the new raw key.

        Raises:
            TenantNotFound: if the tenant does not exist.
        """
        with self._lock:
            row = self._conn.execute(
                "SELECT api_key_hash FROM tenants WHERE id = ? AND deleted_at IS NULL",
                (tenant_id,),
            ).fetchone()
            if row is None:
                raise TenantNotFound(f"tenant not found: {tenant_id}")
            new_key = generate_api_key()
            expires = (datetime.now(UTC) + self.grace_period).isoformat()
            self._conn.execute(
                "INSERT OR REPLACE INTO api_key_grace (tenant_id, old_api_key_hash,"
                " expires_at) VALUES (?, ?, ?)",
                (tenant_id, row["api_key_hash"], expires),
            )
            self._conn.execute(
                "UPDATE tenants SET api_key_hash = ?, updated_at = ? WHERE id = ?",
                (_hasher.hash(new_key), _now_iso(), tenant_id),
            )
            self._conn.commit()
        return new_key

    def soft_delete(self, tenant_id: str) -> None:
        """Archive a tenant by stamping ``deleted_at``. Keeps the row for audit.

        Raises:
            TenantNotFound: if the tenant does not exist or is already deleted.
        """
        with self._lock:
            cur = self._conn.execute(
                "UPDATE tenants SET deleted_at = ?, updated_at = ?"
                " WHERE id = ? AND deleted_at IS NULL",
                (_now_iso(), _now_iso(), tenant_id),
            )
            self._conn.commit()
            if cur.rowcount == 0:
                raise TenantNotFound(f"tenant not found or already deleted: {tenant_id}")


def _verify(stored_hash: str, raw_key: str) -> bool:
    """Argon2 verification; ``False`` on mismatch instead of raising."""
    try:
        return _hasher.verify(stored_hash, raw_key)
    except VerifyMismatchError:
        return False


def _row_to_record(row: sqlite3.Row) -> TenantRecord:
    created = _parse_dt(row["created_at"])
    updated = _parse_dt(row["updated_at"])
    assert created is not None and updated is not None
    return TenantRecord(
        id=row["id"],
        display_name=row["display_name"],
        allowed_models=tuple(json.loads(row["allowed_models"])),
        rate_limits=dict(json.loads(row["rate_limits"])),
        created_at=created,
        updated_at=updated,
        deleted_at=_parse_dt(row["deleted_at"]),
    )
