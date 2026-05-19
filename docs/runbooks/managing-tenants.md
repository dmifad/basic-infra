# Runbook — managing tenants

Create, inspect, rotate and retire tenants. Reference: ADR-0003.

## CLI

Run from the gateway container, or on the host against the bind-mounted DB:

```bash
# in the container
docker compose exec gateway python -m app.tenancy.cli tenant <cmd>

# on the host (TENANT_DB_PATH points at ./tenants/tenants.db)
cd llm/gateway && TENANT_DB_PATH=../../tenants/tenants.db \
    poetry run python -m app.tenancy.cli tenant <cmd>
```

Commands:

```
tenant create --id <id> [--display "<name>"] [--models "*"]
tenant list [--include-deleted]
tenant show <id>
tenant rotate-key <id>          # new key; old one valid 24 h
tenant delete <id> --confirm    # soft delete (archived, kept for audit)
tenant smoke-test <id> [--base-url ...] [--key ...]
```

## Seeding

`make tenants-seed` creates `telcoss` and `pamyat-naroda` (idempotent). It runs
on the host against `./tenants/tenants.db` — the gateway container, which runs
as the host uid, shares that file.

## Notes

- The raw API key is printed **once** on create/rotate. Only an Argon2 hash is
  stored — a lost key must be rotated, not recovered.
- Rotated keys keep working for a 24 h grace window.
- `delete` is a soft delete (`deleted_at` stamped); the row stays for audit.
- Keys for the author's projects live in `~/secrets/basic-infra/<id>.key`.

## Rate limits

Per `(tenant, endpoint)`, token-bucket in Redis. Defaults: chat 60/min,
completions 60/min, embeddings 1000/min, rerank 200/min, models unlimited.
Override per tenant via the `rate_limits` field. If Redis is down the limiter
fails open (`RATE_LIMIT_FAIL_OPEN=true`).
