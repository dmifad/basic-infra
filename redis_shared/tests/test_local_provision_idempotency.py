"""Hermetic redis ACL provisioning-idempotency guard (ADR-0016 §3 / ADR-0017).

Exercises the reset-then-declare `ACL SETUSER` against an EPHEMERAL redis
container — never the live shared redis. Provisioning is a mutation: a live run
would reset the real `app_telcoss` ACL/password. Proves H2b: re-provisioning
converges to a single credential with the namespace-scoped, `@dangerous`-stripped
ACL (no password accumulation).
"""
from __future__ import annotations

from typing import Any

import pytest

pytestmark = pytest.mark.integration

_SECRET = "t3st-secret"


def _as_text(value: Any) -> str:
    """Flatten a redis-py ACL GETUSER field (list/tuple or scalar) to a string."""
    if isinstance(value, (list, tuple)):
        return " ".join(str(v) for v in value)
    return str(value)


@pytest.fixture(scope="module")
def redis_container():  # type: ignore[no-untyped-def]
    from testcontainers.redis import RedisContainer

    with RedisContainer("redis:7.2-alpine") as rc:
        yield rc


@pytest.mark.asyncio
async def test_acl_provision_converges_to_single_credential_when_reprovisioned(
    redis_container,  # type: ignore[no-untyped-def]
) -> None:
    from redis.asyncio import Redis

    from redis_shared.config import AdminSettings
    from redis_shared.local_adapter import LocalAdapter

    host = redis_container.get_container_host_ip()
    port = int(redis_container.get_exposed_port(6379))

    # Point the control plane at the throwaway container's default user (no auth);
    # acl_save off — the bare image has no aclfile, idempotency is in-memory.
    settings = AdminSettings(
        host=host, port=port, username="default", password=None, acl_save=False
    )
    adapter = LocalAdapter(settings=settings, app_password=_SECRET)

    # Idempotent: provisioning twice must not raise (reset prevents accumulation).
    await adapter.provision("telcoss")
    await adapter.provision("telcoss")

    admin = Redis(host=host, port=port, username="default", decode_responses=True)
    try:
        g = await admin.execute_command("ACL", "GETUSER", "app_telcoss")
        assert g is not None, "app_telcoss ACL user missing after provision"

        # redis-py parses GETUSER into a dict; it splits @-categories out of
        # `commands` into a separate `categories` key, so +@all / -@dangerous
        # live under `categories` (check both defensively).
        assert "on" in g["flags"]
        assert len(g["passwords"]) == 1, f"expected one password, got {g['passwords']!r}"

        keys = _as_text(g["keys"])
        assert "~telcoss:*" in keys and "~*" not in keys, f"unexpected keys: {g['keys']!r}"
        assert "&telcoss:*" in _as_text(g["channels"]), f"unexpected channels: {g['channels']!r}"

        cmds = _as_text(g.get("categories")) + " " + _as_text(g.get("commands"))
        assert "+@all" in cmds and "-@dangerous" in cmds, (
            f"unexpected commands/categories: {g!r}"
        )
    finally:
        await admin.aclose()
