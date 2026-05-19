"""Unit tests — rate-limit spec parsing and fail-open behaviour."""
from __future__ import annotations

import pytest

from app.tenancy.ratelimit import DEFAULT_LIMITS, RateLimiter, parse_limit
from app.tenancy.store import TenantRecord


def _tenant(rate_limits: dict[str, str] | None = None) -> TenantRecord:
    return TenantRecord(
        id="t", display_name="T", allowed_models=("*",), rate_limits=rate_limits or {}
    )


@pytest.mark.parametrize(
    ("spec", "expected"),
    [("60/min", (60, 60)), ("1000/min", (1000, 60)), ("5/sec", (5, 1)), ("2/hour", (2, 3600))],
)
def test_parse_limit_valid(spec: str, expected: tuple[int, int]) -> None:
    assert parse_limit(spec) == expected


@pytest.mark.parametrize("spec", ["", "60", "60/year", "abc/min", "/min"])
def test_parse_limit_invalid(spec: str) -> None:
    with pytest.raises(ValueError):
        parse_limit(spec)


def test_limit_for_prefers_tenant_override() -> None:
    limiter = RateLimiter("redis://127.0.0.1:6390/0")
    assert limiter.limit_for(_tenant(), "embeddings") == DEFAULT_LIMITS["embeddings"]
    assert limiter.limit_for(_tenant({"embeddings": "5/min"}), "embeddings") == "5/min"


async def test_enforce_fails_open_when_redis_unreachable() -> None:
    """With Redis down and fail_open=True, enforce accepts the request."""
    limiter = RateLimiter("redis://127.0.0.1:6390/0", fail_open=True)
    try:
        await limiter.enforce(_tenant(), "embeddings")  # must not raise
    finally:
        await limiter.close()


async def test_enforce_unlimited_endpoint_is_noop() -> None:
    limiter = RateLimiter("redis://127.0.0.1:6390/0")
    try:
        await limiter.enforce(_tenant(), "models")  # unlimited -> no Redis call
    finally:
        await limiter.close()
