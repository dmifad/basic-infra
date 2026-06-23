# Authentik DB bootstrap

Authentik owns its own database on the shared `postgres-multi` instance, via a
dedicated **owner role** (`authentik`) — *not* the platform `app_<tenant>`
runtime role (which is DML-only and cannot run Authentik's migrations). See
ADR-0018.

## Apply (admin, idempotent)

Run as the postgres admin against the maintenance DB. Pass the role password as
a psql variable (sourced from `.env` → `AUTHENTIK_PG_PASSWORD`):

```bash
# from ~/basic-infra, with .env loaded:
set -a; . ./.env; set +a
PGPASSWORD="$POSTGRES_MULTI_ADMIN_PASSWORD" \
  psql -h 127.0.0.1 -p "${POSTGRES_MULTI_PORT:-5434}" \
       -U "${POSTGRES_MULTI_ADMIN_USER:-postgres}" -d postgres \
       -v authentik_pw="$AUTHENTIK_PG_PASSWORD" \
       -f authentik/db/bootstrap.sql
```

Re-running is safe (role guarded by `IF NOT EXISTS`, password re-asserted; DB
guarded by `\gexec` existence check).

## Backup

There is no automated backup target in this repo — backup is the per-DB manual
`pg_dump -Fc` procedure in `docs/runbooks/postgres-adoption.md` §4. **Add the
`authentik` database to that rotation** alongside `telcoss`:

```bash
PGPASSWORD=... pg_dump -h 127.0.0.1 -p 5434 -U postgres -Fc authentik > authentik.dump
```
