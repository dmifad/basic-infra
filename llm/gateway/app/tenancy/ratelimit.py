"""Per-tenant rate limiting (ADR-0003).

A fixed-window counter per ``(tenant_id, endpoint)`` backed by the platform's
Redis. If Redis is unreachable the limiter *fails open* by default
(``RATE_LIMIT_FAIL_OPEN``) — better to accept some traffic than reject all of it
during a Redis blip.
"""
from __future__ import annotations

import time

import redis.asyncio as aioredis

from ..exceptions import BackendUnavailableError, RateLimitError
from ..observability.logging import get_logger
from .store import TenantRecord

_log = get_logger("ratelimit")

# Default limits per ADR-0003. ``None`` means unlimited.
DEFAULT_LIMITS: dict[str, str | None] = {
    "chat.completions": "60/min",
    "completions": "60/min",
    "embeddings": "1000/min",
    "rerank": "200/min",
    "models": None,
}

_WINDOW_SECONDS: dict[str, int] = {
    "sec": 1, "s": 1,
    "min": 60, "m": 60,
    "hour": 3600, "h": 3600,
}


def parse_limit(spec: str) -> tuple[int, int]:
    """Parse a limit string like ``"60/min"`` into ``(count, window_seconds)``.

    Raises:
        ValueError: if the spec is not ``<int>/<sec|min|hour>``.
    """
    count_str, _, unit = spec.partition("/")
    window = _WINDOW_SECONDS.get(unit.strip().lower())
    if window is None or not count_str.strip().isdigit():
        raise ValueError(f"invalid rate-limit spec: {spec!r}")
    return int(count_str), window


class RateLimiter:
    """Fixed-window rate limiter over Redis."""

    def __init__(self, redis_url: str, *, fail_open: bool = True) -> None:
        # redis-py's from_url is not type-annotated; the target type is explicit.
        self._redis: aioredis.Redis = aioredis.from_url(  # type: ignore[no-untyped-call]
            redis_url, decode_responses=True
        )
        self._fail_open = fail_open

    async def close(self) -> None:
        """Close the Redis connection pool."""
        await self._redis.aclose()

    def limit_for(self, tenant: TenantRecord, endpoint: str) -> str | None:
        """Return the effective limit spec for ``endpoint`` — tenant override or default."""
        if endpoint in tenant.rate_limits:
            return tenant.rate_limits[endpoint]
        return DEFAULT_LIMITS.get(endpoint)

    async def enforce(self, tenant: TenantRecord, endpoint: str) -> None:
        """Count this request against the tenant's window for ``endpoint``.

        Raises:
            RateLimitError: if the tenant has exceeded the window (429).
            BackendUnavailableError: if Redis is down and ``fail_open`` is false.
        """
        spec = self.limit_for(tenant, endpoint)
        if spec is None:
            return  # unlimited endpoint
        count, window = parse_limit(spec)

        now = int(time.time())
        bucket = now // window
        key = f"rl:{tenant.id}:{endpoint}:{bucket}"
        try:
            current = await self._redis.incr(key)
            if current == 1:
                await self._redis.expire(key, window)
        except (aioredis.RedisError, OSError) as exc:
            if self._fail_open:
                _log.warning("ratelimit_fail_open", endpoint=endpoint, error=str(exc))
                return
            raise BackendUnavailableError(
                "rate limiter unavailable", code="ratelimit_unavailable"
            ) from exc

        if current > count:
            retry_after = window - (now % window)
            raise RateLimitError(
                f"rate limit exceeded for {endpoint}: {spec}",
                retry_after=max(retry_after, 1),
            )
