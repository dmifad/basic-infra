#!/usr/bin/env python3
"""Seed the default tenants (telcoss, pamyat-naroda).

Idempotent — re-running creates only what is missing and never overwrites an
existing tenant. Reads the tenant DB path from ``TENANT_DB_PATH`` (defaults to
the gateway's configured path).

Run via the gateway's Poetry environment, e.g.::

    make tenants-seed
    # or
    cd llm/gateway && TENANT_DB_PATH=../../tenants/tenants.db \\
        poetry run python ../../scripts/seed-tenants.py

Generated API keys are printed once and cannot be retrieved later — only their
hashes are stored.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Make the gateway's `app` package importable when run from the host.
_GATEWAY = Path(__file__).resolve().parent.parent / "llm" / "gateway"
if str(_GATEWAY) not in sys.path:
    sys.path.insert(0, str(_GATEWAY))

from app.config import Settings  # noqa: E402
from app.tenancy.store import TenantStore  # noqa: E402

SEED_TENANTS = [
    {"id": "telcoss", "display_name": "Telcoss"},
    {"id": "pamyat-naroda", "display_name": "Pamyat-Naroda Graph"},
]


def main() -> int:
    settings = Settings()
    store = TenantStore(settings.tenant_db_path)
    print(f"Tenant store: {settings.tenant_db_path}")
    created: list[tuple[str, str]] = []
    try:
        for seed in SEED_TENANTS:
            tenant_id = seed["id"]
            if store.get(tenant_id) is not None:
                print(f"  [-] {tenant_id}: exists, skipped")
                continue
            record, raw_key = store.create(
                id=tenant_id, display_name=seed["display_name"], allowed_models=("*",)
            )
            created.append((record.id, raw_key))
            print(f"  [+] CREATED {record.id}")
    finally:
        store.close()

    if created:
        print()
        print("=" * 64)
        print("SAVE THESE KEYS NOW — they cannot be retrieved later:")
        for tenant_id, raw_key in created:
            print(f"  {tenant_id:18} {raw_key}")
        print("=" * 64)
    else:
        print("All seed tenants already present — nothing to do.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
