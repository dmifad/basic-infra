#!/usr/bin/env python3
"""Seed default tenants (telcoss, pamyat-naroda).

Idempotent — re-running adds only what's missing, never overwrites existing.
Run from the gateway container or with TENANT_DB_PATH set:

    docker exec -it basic-infra-gateway python -m scripts.seed_tenants
    # or
    TENANT_DB_PATH=./tenants.db python scripts/seed-tenants.py

Output:
    Prints generated api_keys for new tenants. Save them — they cannot be
    retrieved later (only their hash is stored).

TODO(week4-phase-5): implement.
"""
from __future__ import annotations

import sys

# from llm.gateway.app.tenancy.store import TenantStore
# from llm.gateway.app.config import get_settings


SEED_TENANTS = [
    {
        "id": "telcoss",
        "display_name": "Telcoss",
        "allowed_models": ("*",),
    },
    {
        "id": "pamyat-naroda",
        "display_name": "Pamyat-Naroda Graph",
        "allowed_models": ("*",),
    },
]


def main() -> int:
    # TODO(week4-phase-5):
    # 1. Load Settings
    # 2. Open TenantStore at settings.tenant_db_path
    # 3. For each seed:
    #    - if store.get(seed.id) exists: print "exists, skipped"
    #    - else: create, capture raw key, print "CREATED <id> KEY=<raw>"
    # 4. Always print final reminder to save keys
    raise NotImplementedError("week4-phase-5")


if __name__ == "__main__":
    sys.exit(main())
