"""Bearer-token authentication.

Wraps :class:`~app.tenancy.store.TenantStore` with a short-lived in-memory
cache (ADR-0003 § "reads are cached in-memory"). Argon2 verification is
deliberately slow; caching keeps the hot path fast without weakening the at-rest
hash. Only positive results are cached, and only briefly.
"""
from __future__ import annotations

import time

from .store import TenantRecord, TenantStore

_CACHE_TTL_SECONDS = 30.0
_CACHE_MAX_ENTRIES = 256


class Authenticator:
    """Resolves raw API keys to tenants, with a small TTL cache."""

    def __init__(
        self,
        store: TenantStore,
        *,
        cache_ttl: float = _CACHE_TTL_SECONDS,
        cache_max: int = _CACHE_MAX_ENTRIES,
    ) -> None:
        self._store = store
        self._cache_ttl = cache_ttl
        self._cache_max = cache_max
        self._cache: dict[str, tuple[float, TenantRecord]] = {}

    def authenticate(self, raw_api_key: str) -> TenantRecord | None:
        """Return the tenant for ``raw_api_key``, or ``None`` if it is invalid.

        A successful lookup is cached for ``cache_ttl`` seconds. The cache is
        bounded; a rotated or deleted key still authenticates (or stops doing so)
        within one TTL window.
        """
        now = time.monotonic()
        cached = self._cache.get(raw_api_key)
        if cached is not None:
            inserted_at, cached_record = cached
            if now - inserted_at < self._cache_ttl:
                return cached_record
            del self._cache[raw_api_key]

        record = self._store.authenticate(raw_api_key)
        if record is not None:
            self._remember(raw_api_key, record, now)
        return record

    def invalidate(self, raw_api_key: str) -> None:
        """Drop a key from the cache (e.g. after rotation in the same process)."""
        self._cache.pop(raw_api_key, None)

    def _remember(self, raw_api_key: str, record: TenantRecord, now: float) -> None:
        if len(self._cache) >= self._cache_max:
            oldest = min(self._cache, key=lambda k: self._cache[k][0])
            del self._cache[oldest]
        self._cache[raw_api_key] = (now, record)
