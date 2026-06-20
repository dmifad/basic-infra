"""CLI control-plane для postgres-multi (provision/deprovision).

Читает admin-креды из env (``POSTGRES_MULTI_*``), вызывает
:class:`postgres.LocalAdapter`. Предназначен для bootstrap/деплоя, не для
горячего пути.

    PYTHONPATH=. python -m postgres.cli provision telcoss
    PYTHONPATH=. python -m postgres.cli deprovision telcoss --confirm  # требует --confirm

deprovision REQUIRES --confirm; missing → rc 2 ("guard refused"), mirroring the
redis-shared double-gate so a tenant DB can never be dropped by a bare invocation.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys

from ._local import LocalAdapter
from ._port import TenantId


def _adapter(*, allow_destructive: bool) -> LocalAdapter:
    return LocalAdapter(
        host=os.environ.get("POSTGRES_MULTI_HOST", "localhost"),
        port=int(os.environ.get("POSTGRES_MULTI_PORT", "5434")),
        admin_user=os.environ.get("POSTGRES_ADMIN_USERNAME", "postgres"),
        admin_password=os.environ.get(
            "POSTGRES_ADMIN_PASSWORD", "changeme-please"
        ),
        allow_destructive=allow_destructive,
        # Secret for the least-privilege runtime role (ADR-0016 §2), canonical
        # platform env name. Absent → role provisioning is skipped.
        app_password=os.environ.get("POSTGRES_APP_PASSWORD"),
    )


async def _provision(tenant: str) -> int:
    adapter = _adapter(allow_destructive=False)
    if not await adapter.health():
        print("postgres-multi недоступен (проверь make up-postgres)", file=sys.stderr)
        return 2
    await adapter.provision(TenantId(tenant))
    print(f"provisioned: {tenant}")
    return 0


async def _deprovision(tenant: str, *, confirm: bool) -> int:
    if not confirm:
        print(
            "refusing to deprovision without --confirm "
            "(this drops the tenant's database)",
            file=sys.stderr,
        )
        return 2
    adapter = _adapter(allow_destructive=True)
    await adapter.deprovision(TenantId(tenant))
    print(f"deprovisioned: {tenant}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="postgres.cli")
    sub = parser.add_subparsers(dest="command", required=True)

    p_prov = sub.add_parser("provision", help="создать tenant-БД + PostGIS")
    p_prov.add_argument("tenant")

    p_deprov = sub.add_parser("deprovision", help="удалить tenant-БД")
    p_deprov.add_argument("tenant")
    p_deprov.add_argument(
        "--confirm",
        action="store_true",
        help="required: confirms destructive removal of the tenant database",
    )

    args = parser.parse_args(argv)
    if args.command == "provision":
        return asyncio.run(_provision(args.tenant))
    if args.command == "deprovision":
        return asyncio.run(_deprovision(args.tenant, confirm=args.confirm))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
