# ADR-0014 — Shared Redis layer (ACL-tenant + key-namespace)

- **Status:** Accepted
- **Date:** 2026-06-04
- **Track:** Platform (basic-infra), Week 9
- **Relates to:** follows the control-plane + SDK + profile pattern of ADR-0013
  (postgres-multi); coexistence/port discipline of ADR-0011/0012.

## Context

Client projects (telcoss, pamyat) need Redis for caching, sessions, rate limits
and lightweight queues. basic-infra already runs a Redis for the LLM gateway
(`llm/compose/compose.redis.yml`), but that is internal to the LLM stack. We want
a *shared platform* Redis offered to client projects with tenant isolation —
analogous to postgres-multi's database-per-project, but for Redis.

Redis isolation options: db-number (max 16, SELECT-based, discouraged, weak
per-db ACL), key-prefix namespacing, or ACL users restricted to a key/channel
pattern. Constraints carried in: profile-gated, shifted loopback port,
replace-not-coexist for client adoption (Week 12), ENV-split discipline, and the
bridge-v14 lesson that `deprovision` needs a confirmation guard.

## Decision

1. **Single shared Redis 7.2**, tenant isolation by **ACL user + key-prefix
   namespace on db 0** — not by db number. The control plane provisions
   `app_<namespace>` with `~<namespace>:*` (keys) and `&<namespace>:*`
   (pub/sub channels), `+@all -@dangerous` (no FLUSHALL/CONFIG/etc.). The ACL
   pattern enforces the namespace server-side even if a client forgets to prefix.

2. **Control plane `redis_shared/`** (NOT `redis/` — that name shadows the
   `redis` pip library and breaks `from redis.asyncio import …`): `RedisProvisioningPort`
   + `LocalAdapter` (real ACL SETUSER/DELUSER via an admin connection, ACL SAVE
   to persist) + `ManagedAdapter` (stub provision, working health — for managed
   Redis where ACLs are created out-of-band) + `cli`.

3. **Data plane SDK `basic_infra_redis_client`** (hatchling/PEP 621, flat layout,
   `py.typed`): `RedisSettings` (env prefix `BASIC_INFRA_REDIS_`, explicit
   `…_ENV`, no AliasChoices), async/sync client factories, `RedisNamespace`
   key-prefixer, health, tenant→namespace/username derivation
   (hyphen→underscore, mirroring postgres-multi).

4. **`deprovision` is double-gated from day one**: the CLI requires `--confirm`
   (and `--purge` of namespace keys also requires it); the Makefile target
   additionally requires `CONFIRM=yes`. This is the guard postgres-multi's
   `deprovision` still lacks (bridge v14 follow-up).

5. **Profile `redis-shared`, shifted host port 6380** (loopback), separate from
   the LLM redis. Persistence (AOF) on the **NVMe** hot tier
   (`/home/vams/telcoss-data/redis-shared`), not the HDD tier. In-network clients
   use `redis-shared:6379`; the shifted host port is debug/admin only and flips
   to canonical at the Week 11/12 cutover.

## Coexistence (host loopback ports)

| Service | Component | Host port | Profile |
|---|---|---|---|
| basic-infra | Prometheus / Loki / Grafana | 9190 / 3110 / 3002 | observability |
| basic-infra | Tempo (HTTP/OTLP) | 3210 / 4417 / 4418 | tracing |
| basic-infra | PostgreSQL (postgres-multi) | 5434 | postgres |
| **basic-infra** | **Redis (shared)** | **6380** | **redis-shared** |
| basic-infra | Redis (LLM stack) | see llm/compose/compose.redis.yml | — |
| basic-infra | LLM gateway | 8013 | — |
| telcoss | PostgreSQL | 5433 | — |

## Consequences

Positive: one shared Redis for all client projects; strong-ish logical isolation
via ACL+namespace; cheap (single instance); the CONFIRM guard makes destructive
ops safe.

Costs / follow-ups: single instance = shared blast radius (a noisy tenant can
exhaust memory — `maxmemory-policy noeviction` surfaces it rather than silently
evicting; per-tenant memory accounting is future work). Admin password lives in
the (templated, non-public) aclfile until a secrets manager is wired.
OTEL redis instrumentation for client spans is an optional adoption step
(see runbook), not part of this layer.

## Alternatives considered

- **db-number per tenant**: rejected — capped at 16, SELECT-based, weak ACLs.
- **Separate Redis instance per tenant**: rejected — heavy for ~1k–5k-sub
  operators; revisit only if blast-radius isolation becomes a hard requirement.
- **Reuse the LLM redis**: rejected — different lifecycle/purpose; keep platform
  and LLM-internal concerns separate.
- **Naming the control plane `redis/`**: rejected — shadows the `redis` pip
  package.
