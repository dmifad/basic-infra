"""Postgres control-plane deprovision CONFIRM-guard tests (ADR-0013).

Mirrors the redis-shared double-gate: a bare `deprovision` refuses with the
distinct rc 2 ("guard refused"); with `--confirm` the destructive op proceeds.
The adapter is mocked so the proceed-path needs no live instance (throwaway
tenant).
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

from postgres.cli import main


def test_deprovision_without_confirm_refuses_rc2() -> None:
    assert main(["deprovision", "throwaway-tenant"]) == 2


def test_deprovision_with_confirm_proceeds_against_throwaway() -> None:
    fake_adapter = AsyncMock()
    with patch("postgres.cli._adapter", return_value=fake_adapter) as build_adapter:
        rc = main(["deprovision", "throwaway-tenant", "--confirm"])
    assert rc == 0
    build_adapter.assert_called_once_with(allow_destructive=True)
    fake_adapter.deprovision.assert_awaited_once()
