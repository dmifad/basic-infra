"""Least-privilege ACL re-provision — DB-free guard (ADR-0016 §3).

The reset-then-declare `SETUSER` itself (exactly one password = the secret,
namespace scope, re-run idempotency) belongs in a follow-up integration test
against a throwaway redis — none in this suite yet (flagged in ADR-0016 §3).
Here we cover the contract that needs no live redis: a missing app-password
secret is rejected outright rather than minting a random, non-recoverable one.
"""
from __future__ import annotations

import pytest

from redis_shared.local_adapter import LocalAdapter


async def test_provision_requires_app_password() -> None:
    """No BASIC_INFRA_REDIS_APP_PASSWORD → provision raises before connecting."""
    adapter = LocalAdapter(app_password=None)
    with pytest.raises(ValueError):
        await adapter.provision("telcoss")
