"""Integration tests — rate limiting against a real Redis (testcontainers)."""
from __future__ import annotations

from collections.abc import Iterator

import pytest

from app.exceptions import RateLimitError
from app.tenancy.ratelimit import RateLimiter
from app.tenancy.store import TenantRecord


@pytest.fixture(scope="module")
def redis_url() -> Iterator[str]:
    """A throwaway Redis 7 container; yields its connection URL."""
    from testcontainers.redis import RedisContainer

    with RedisContainer("redis:7-alpine") as container:
        host = container.get_container_host_ip()
        port = container.get_exposed_port(6379)
        yield f"redis://{host}:{port}/0"


def _tenant(tenant_id: str, limits: dict[str, str]) -> TenantRecord:
    return TenantRecord(
        id=tenant_id, display_name=tenant_id, allowed_models=("*",), rate_limits=limits
    )


async def test_enforce_blocks_after_limit(redis_url: str) -> None:
    tenant = _tenant("rl-block", {"embeddings": "3/min"})
    limiter = RateLimiter(redis_url)
    try:
        for _ in range(3):
            await limiter.enforce(tenant, "embeddings")
        with pytest.raises(RateLimitError) as caught:
            await limiter.enforce(tenant, "embeddings")
        assert caught.value.status_code == 429
        assert caught.value.retry_after >= 1
    finally:
        await limiter.close()


async def test_tenants_have_independent_buckets(redis_url: str) -> None:
    tenant_a = _tenant("rl-a", {"rerank": "1/min"})
    tenant_b = _tenant("rl-b", {"rerank": "1/min"})
    limiter = RateLimiter(redis_url)
    try:
        await limiter.enforce(tenant_a, "rerank")
        await limiter.enforce(tenant_b, "rerank")  # separate bucket — allowed
        with pytest.raises(RateLimitError):
            await limiter.enforce(tenant_a, "rerank")
    finally:
        await limiter.close()
