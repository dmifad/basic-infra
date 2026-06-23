# 0018 — Authentik as the platform IdP

* **Status:** Accepted
* **Date:** 2026-06-23
* **Relates to:** ADR-0013 (postgres-multi), ADR-0014 (redis-shared), ADR-0016
  (pre-prod hardening / least-privilege roles); telcoss ADR (J1 — telcoss as an
  OIDC relying party, paired)

## Context

telcoss authenticates with a single shared bearer token (`settings.api_token` →
a fixed admin `UserId`), explicitly marked a *pre-Authentik* placeholder. There
is no per-user identity, login flow, or SSO. As more products land on the shared
engine (Inventory, M&A, Wiki) a real identity provider is needed — one that
lives at the **platform** layer (basic-infra), not inside any single product, so
every client project federates against the same IdP.

basic-infra already hosts the shared control-plane infra: `postgres-multi`
(database-per-tenant), `redis-shared` (ACL-namespaced), observability + tracing,
all on the external `basic-infra-net`. Authentik is the natural fit: self-hosted,
OIDC/OAuth2/SAML, Postgres + Redis backed — it slots into the existing stack.

## Decision

1. **Authentik runs as a platform service in basic-infra**, profile-gated under
   `["authentik"]` (`authentik/compose/authentik.yml`, added to the root
   `include:`). `server` + `worker` on a **pinned** image tag
   (`ghcr.io/goauthentik/server:2026.5.3`, never `:latest` — reproducibility).
   Ports bind **loopback only**: `127.0.0.1:9002→9000` (HTTP) and `9444→9443`
   (HTTPS) — shifted off `:9000` because **MinIO already publishes host `:9000`**
   (the one platform service not loopback-scoped). Follows the established
   shifted-port + loopback convention.

2. **Authentik gets a DEDICATED OWNER role on its own DB — NOT `app_authentik`.**
   The platform `app_<tenant>` runtime role is intentionally DML-only
   (`NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS`, no DDL — ADR-0016 §2).
   Authentik is a **self-migrating tenant**: it issues `CREATE TABLE`/DDL on every
   release. So it owns its database (`CREATE DATABASE authentik OWNER authentik`)
   via a separate `authentik` LOGIN role — ownership confers DDL on its own
   objects and nothing platform-wide. This is created by an idempotent,
   admin-run `authentik/db/bootstrap.sql`, **not** `make provision` (which would
   create an admin-owned DB plus a spurious `app_authentik` DML role).
   **Consequence: H2a is untouched** — `app_telcoss` least-privilege is not
   loosened; Authentik's elevated rights are scoped to its own database only.

3. **A dedicated `authentik-redis` (redis:7-alpine), NOT `redis-shared`.**
   Authentik uses Redis as cache + Celery task broker and expects a whole
   keyspace with no ACL constraints. `redis-shared` is ACL-namespaced
   (`app_<tenant>` ~ns:* scope — ADR-0014/0016 §3); forcing Authentik into that
   namespace fights its assumptions. A throwaway dedicated instance (internal,
   no published port) keeps the shared ACL model clean. Its data is a cache/broker
   — not durable state — so a plain docker-managed volume suffices.

4. **Observability:** server + worker carry `basic-infra.observability.logs:
   "true"` + `.service`/`.env` labels → Promtail's docker-SD log scrape picks
   them up automatically. **Metrics are deferred:** Prometheus scrapes via static
   `static_configs` jobs (the label-based `docker_sd` path is commented out), so
   wiring Authentik's `:9300/metrics` is a follow-up `prometheus.yml` edit, not
   part of this change.

5. **No docker socket on the worker** — OIDC-only deployment. The socket (needed
   for Authentik *outposts*: proxy/LDAP providers) is mounted later only if/when
   an outpost provider is introduced. Smaller attack surface by default.

6. **telcoss becomes an OIDC relying party** in a paired J1 telcoss-side ADR: the
   shared-token bearer is replaced by Authentik-issued OIDC, `require_user`
   resolving a real per-user identity. Out of scope for this (infra) ADR.

## Consequences

* One platform IdP for all current and future products; per-user identity + SSO
  become available without per-product auth stacks.
* Backup: there is no automated pg backup target — backup is the manual per-DB
  `pg_dump -Fc` runbook (`docs/runbooks/postgres-adoption.md` §4). The **operator
  must add the `authentik` DB to that rotation** (noted in `authentik/db/README.md`).
* Secrets (`AUTHENTIK_SECRET_KEY`, `AUTHENTIK_PG_PASSWORD`,
  `AUTHENTIK_BOOTSTRAP_PASSWORD`) live in git-ignored `.env`; compose fails closed
  (`${VAR:?…}`) if any is missing.
* Authentik's DDL privileges are confined to its own database; the least-privilege
  posture of every other tenant (incl. telcoss `app_telcoss`) is unchanged.
* Image tag is pinned — bumping Authentik is a deliberate, reviewed change.
