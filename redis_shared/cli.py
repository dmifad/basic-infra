"""Shared Redis control-plane CLI.

    python -m redis.cli provision   --tenant telcoss
    python -m redis.cli deprovision --tenant telcoss --confirm [--purge]
    python -m redis.cli health

deprovision REQUIRES --confirm (and --purge additionally requires --confirm)
so a tenant's access/keys can never be dropped by a bare invocation — the same
CONFIRM-guard discipline the postgres-multi deprovision now also enforces.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

from .local_adapter import LocalAdapter
from .port import RedisProvisioningPort


def _adapter() -> RedisProvisioningPort:
    # Consume-and-reassert: the tenant ACL password is the operator secret
    # (ADR-0016 §3), aligned with the client SDK prefix (BASIC_INFRA_REDIS_*).
    return LocalAdapter(app_password=os.environ.get("BASIC_INFRA_REDIS_APP_PASSWORD"))


async def _provision(tenant: str) -> int:
    creds = await _adapter().provision(tenant)
    # The password is the operator-supplied secret — never echo it (nor the full
    # DSN); mask the password in the DSN and point at the env var.
    masked_dsn = creds.dsn.replace(f":{creds.password}@", ":***@")
    print(f"provisioned: {creds.tenant}")
    print(f"username   : {creds.username}")
    print(f"namespace  : {creds.namespace}")
    print(f"dsn        : {masked_dsn}")
    print("credential : BASIC_INFRA_REDIS_APP_PASSWORD (as supplied)")
    return 0


async def _deprovision(tenant: str, purge: bool) -> int:
    await _adapter().deprovision(tenant, purge=purge)
    print(f"deprovisioned {tenant}" + (" (+purged namespace keys)" if purge else ""))
    return 0


async def _health() -> int:
    ok = await _adapter().health()
    print("ok" if ok else "unreachable")
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="redis.cli")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("provision")
    p.add_argument("--tenant", required=True)

    d = sub.add_parser("deprovision")
    d.add_argument("--tenant", required=True)
    d.add_argument("--confirm", action="store_true",
                   help="required: confirms destructive removal of the ACL user")
    d.add_argument("--purge", action="store_true",
                   help="also delete the tenant's namespace keys (needs --confirm)")

    sub.add_parser("health")

    args = parser.parse_args(argv)

    if args.command == "provision":
        return asyncio.run(_provision(args.tenant))
    if args.command == "deprovision":
        if not args.confirm:
            print(
                "refusing to deprovision without --confirm "
                "(this removes the tenant's ACL user)",
                file=sys.stderr,
            )
            return 2
        return asyncio.run(_deprovision(args.tenant, args.purge))
    if args.command == "health":
        return asyncio.run(_health())
    return 2  # pragma: no cover - argparse enforces a subcommand


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
