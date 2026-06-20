"""Least-privilege runtime-role provisioning — DB-free guard (ADR-0016 §2).

The grant logic itself (role attributes, DML-allowed/DDL-denied, re-run
idempotency) belongs in a follow-up integration test against a throwaway
PostGIS instance — no such fixture exists in this suite yet (flagged in
ADR-0016 §2). Here we cover the contract that needs no live DB: an empty
runtime-role password is rejected outright rather than silently setting a weak
credential.
"""
from __future__ import annotations

import pytest

from postgres._local import LocalAdapter
from postgres._port import TenantId


def _adapter() -> LocalAdapter:
    return LocalAdapter(
        host="localhost", port=5434, admin_user="postgres", admin_password="x"
    )


async def test_grant_runtime_role_rejects_empty_password() -> None:
    """An empty password raises before any connection is attempted."""
    with pytest.raises(ValueError):
        await _adapter().grant_runtime_role(TenantId("telcoss"), "")
