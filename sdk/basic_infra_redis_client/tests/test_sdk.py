"""Unit tests for basic_infra_redis_client (no live Redis).

Convention: test_<what>_<when>, no classes. Connection/health tests that need a
server are marked `integration` and deselected by default.
"""

import pytest

from basic_infra_redis_client import (
    RedisNamespace,
    RedisSettings,
    derive_namespace,
    derive_username,
)


def test_namespace_derivation_normalises_tenant():
    assert derive_namespace("My-Tenant") == "my_tenant"
    assert derive_namespace("telcoss") == "telcoss"
    assert derive_namespace("a..b--c") == "a_b_c"


def test_namespace_derivation_rejects_empty():
    with pytest.raises(ValueError):
        derive_namespace("---")


def test_username_derivation_prefixes_app():
    assert derive_username("telcoss") == "app_telcoss"
    assert derive_username("My-Tenant") == "app_my_tenant"


def test_namespaced_key_prefixes():
    ns = RedisNamespace("telcoss")
    assert ns.key("session:42") == "telcoss:session:42"


def test_settings_read_env_prefix(monkeypatch):
    monkeypatch.setenv("BASIC_INFRA_REDIS_HOST", "redis-shared")
    monkeypatch.setenv("BASIC_INFRA_REDIS_PORT", "6380")
    monkeypatch.setenv("BASIC_INFRA_REDIS_TENANT", "telcoss")
    monkeypatch.setenv("BASIC_INFRA_REDIS_USERNAME", "app_telcoss")
    monkeypatch.setenv("BASIC_INFRA_REDIS_PASSWORD", "secret")
    s = RedisSettings()
    assert s.port == 6380
    assert s.namespace == "telcoss"
    assert s.namespacer().key("k") == "telcoss:k"


def test_settings_env_is_not_app_env(monkeypatch):
    monkeypatch.setenv("ENV", "production")
    monkeypatch.delenv("BASIC_INFRA_REDIS_ENV", raising=False)
    assert RedisSettings().env == "local"


def test_dsn_includes_acl_credentials():
    s = RedisSettings(
        host="redis-shared", port=6380, username="app_telcoss",
        password="secret", tenant="telcoss",
    )
    assert s.dsn() == "redis://app_telcoss:secret@redis-shared:6380/0"


def test_dsn_uses_rediss_when_ssl():
    s = RedisSettings(host="h", port=6380, ssl=True, password="p")
    assert s.dsn().startswith("rediss://:p@h:6380/0")


@pytest.mark.integration
async def test_health_pings_live_server():
    # Live-server connectivity probe (NOT hermetic): exercises check_health against
    # the env-configured ACL redis. Skip when no server is reachable — check_health
    # swallows all errors into False, so a direct ping is used to distinguish
    # "unreachable" from "unhealthy". When a server DOES answer, the real health
    # assertion is kept.
    from basic_infra_redis_client import (
        RedisSettings,
        check_health,
        create_async_client,
    )

    probe = create_async_client(RedisSettings())
    try:
        await probe.ping()
    except Exception:
        pytest.skip("live ACL redis not reachable")
    finally:
        await probe.aclose()

    assert await check_health() is True
