# ADR-0016 — Pre-prod hardening: gateway upstream-pool resilience and per-tenant least-privilege provisioning

- **Status:** Proposed (accept on apply)
- **Date:** 2026-06-17
- **Context repo:** basic-infra
- **Track:** H (pre-prod hardening)
- **Supersedes:** draft `coordination/track-BCH/adr/ADR-0016-pre-prod-hardening.md` — mis-numbered as a telcoss
  record. telcoss next-free ADR is **0015**, basic-infra next-free is **0016**. This record is basic-infra 0016
  (platform-side decisions). telcoss-side adoption (runtime DSN switch, `/health` green-up, eval-bypass-revert
  documentation) is recorded separately as **telcoss ADR-0015** (forthcoming with phases H3/H4).

## Context

Tracks B (ADR-0009 compliance gate) and C (merges → `main`, pushed) are closed. The Track-H inspection
(`coordination/track-BCH/inspection-H-2026-06-17.md`, read-only) surfaced three basic-infra-side
reliability/security gaps and corrected two stale premises from the bridge.

**Real gaps (basic-infra):**

1. **Gateway upstream httpx pool stall 🔴 (prod inference blocker).** `backends/base.py:68` builds
   `httpx.AsyncClient(timeout=float(timeout_seconds))` — a *blanket scalar* (connect = read = pool = 900s from
   `backends.yaml`), with no `Limits` and no keepalive tuning. The client is built once at lifespan
   (`Registry.load`), reused for the gateway's whole lifetime; the only teardown is `registry.aclose()` at
   shutdown. `HealthChecker` merely flips a bool — it does **not** rebuild or drain the pool on recovery.
   Mechanism (matches the observed *swallowed-POST / backend-idle / health-200* signature): after a backend
   recreate, a POST grabs a stale keepalive connection to the recreated backend and hangs on the 900s blanket
   read timeout, while the 5s health GET opens a fresh connection and keeps returning 200. Also: the
   `config.backend_request_timeout_seconds` knob is **dead** (unused), `BACKEND_REQUEST_TIMEOUT_SECONDS` is
   **not** in the compose `environment:`, `/metrics` is a TODO stub (no pool gauges), and SIGHUP reload is
   known-broken.

2. **No least-privilege Postgres role.** Only the `postgres` superuser exists; `_local.py:60-83` provisions
   `CREATE DATABASE` + PostGIS only — no role/grant — so telcoss runs as the admin superuser.

3. **Redis re-provision is non-idempotent.** `local_adapter.py:39-72` mints a fresh password on every call and
   uses `resetkeys`/`resetchannels` (not `resetpass`); passwords accumulate and the one-time value is
   unrecoverable. This — not persistence — is the root cause of the "`app_telcoss` redis credential
   unprovisioned" symptom from C-verify.

**Stale premises corrected (recorded, not actioned):**

- Redis **ACL persistence already works** — `app_telcoss` is in `users.acl` (hashed), `aclfile` is configured.
  The earlier "ACL persistence" framing was wrong; the real issue is re-provision idempotency (gap 3).
- The **pg deprovision CONFIRM guard already exists** (`Makefile:157-163` `exit 2` + CLI `--confirm`); the draft
  item and the `Makefile:221` "still lacks" comment are stale → dropped.
- **Port:** live `postgres-multi` is **:5434**; runbook/draft `:5433` is stale. DSN work (telcoss ADR-0015)
  must target the verified instance, not assume 5433.

## Decision

### 1. Gateway pool resilience (phase H1)
- Replace the blanket scalar with a **structured** `httpx.Timeout(connect=5s, write=10s, pool=5s,
  read=<per-backend `timeout_seconds`, default = `config.backend_request_timeout_seconds` (900s)>)` —
  fail-fast on connect/pool acquisition, preserve the long read for legitimate inference. Read caps stay
  per-backend: tpro=900s, tei-embed=60s, tei-rerank=60s.
- Add `httpx.Limits(max_keepalive_connections=20, keepalive_expiry=30s)` so stale pooled connections are
  evicted within a bounded window.
- **Health-driven reconnect:** on a `HealthChecker` down→up edge (`record_health` returns the recovery edge,
  fired exactly once per recovery), gracefully rebuild the affected backend's `AsyncClient` — swap the
  reference atomically (new requests hit the fresh pool immediately) and defer-`aclose()` the old client with
  **grace = the backend's read cap** (tpro 900s / TEI 60s) so the longest possible in-flight request drains
  before the old pool closes. This drops connections to a recreated backend rather than reusing them.
- **Wire the dead knob:** drive the read timeout from `config.backend_request_timeout_seconds`; export
  `BACKEND_REQUEST_TIMEOUT_SECONDS` in the compose `environment:` section (not just `.env`) so it reaches the
  container (prior learning).
- **Known bounded residual → bug-ledger:** a *sub-interval* recreate (backend churns and recovers entirely
  within one health interval, so no probe ever fails) raises no recovery edge, so an in-use stale keepalive
  conn can still hang until its **read cap** (≤ tpro 900s). Bounded, not unbounded. Mitigation: keep the
  health interval **<** `keepalive_expiry` (30s) so a stale idle conn is evicted by the pool before reuse;
  full closure would need active in-request retry/probe (deferred).
- **Out of scope → bug-ledger:** SIGHUP reload fix, `/metrics` pool gauges.

### 2. Least-privilege Postgres role (phase H2a)
- Provision a per-tenant **least-privilege** role (`app_telcoss`, runtime DML) distinct from the owner/admin
  role used to run migrations. Use **schema-level GRANTs + `ALTER DEFAULT PRIVILEGES`** so the role is valid
  independent of migration timing (decouples role provisioning from when 0008–0010 are applied). The runtime
  DSN switches off the superuser on the telcoss side (ADR-0015).

  **Locked grant model** (`postgres/_local.py::grant_runtime_role`, idempotent / re-runnable):
  - **Consume-and-reassert credential.** The role password is read from a required secret
    (`BASIC_INFRA_POSTGRES_APP_PASSWORD`, aligned with the client SDK prefix); absent → role provisioning is
    skipped (DB-only, back-compat). Empty → hard error (no weak default). Every run re-asserts the password and
    attributes (`LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS`), so the credential is always current.
  - **Server-side `%I`/`%L` quoting.** The password is passed as a real bind parameter into a
    transaction-local GUC (`set_config('telcoss.app_pw', $1, true)`) and applied via
    `format('ALTER ROLE %I … PASSWORD %L', role, current_setting(…))` inside a `DO` block — no manual escaping,
    no dependency on `standard_conforming_strings`, no password in statement text; the GUC is dropped at commit.
  - **grant-sync for schema USAGE.** `ALTER DEFAULT PRIVILEGES` has **no schema-level form**, so per-schema
    `USAGE` + `SELECT,INSERT,UPDATE,DELETE ON ALL TABLES` + `USAGE,SELECT ON ALL SEQUENCES` is (re)applied by
    looping every non-system, non-`public` schema. New schemas (e.g. `compliance`/`configs` from 0008/0009) are
    picked up by **re-running grant-sync post-migration** (H4 runbook).
  - **Narrow PostGIS set in `public`.** `USAGE` + `EXECUTE ON ALL FUNCTIONS` + `SELECT` on the present subset of
    `spatial_ref_sys` / `geometry_columns` / `geography_columns` — **no** blanket `SELECT` on `public`, **nothing**
    on `alembic_version`.
  - **Future objects.** `ALTER DEFAULT PRIVILEGES FOR ROLE <owner>` **database-wide** (no `IN SCHEMA`) grants DML
    on tables + `USAGE,SELECT` on sequences the migration-runner creates later — covers future-schema tables
    without re-running.
  - Migrations continue to run as the owner/superuser; only the **runtime** DSN switches to `app_telcoss`
    (telcoss ADR-0015 / H3). Integration test (role attributes · DML-allowed/DDL-denied · re-run idempotency)
    against a throwaway PostGIS is a **follow-up** — no such fixture in the suite yet.

### 3. Redis re-provision idempotency (phase H2b)
- Make provisioning **recoverable/idempotent** — stable or recoverable credential path instead of minting +
  orphaning a fresh password per call; verify survive-recreate; set prod data ownership (`chown 999`). Keep
  `aclfile` persistence as-is.

  **Locked redis model** (`redis_shared/local_adapter.py::provision`, mirrors the pg §2 design):
  - **Consume-and-reassert, required secret.** The tenant ACL password is the operator secret
    `BASIC_INFRA_REDIS_APP_PASSWORD` (aligned with the client SDK prefix `BASIC_INFRA_REDIS_*`); absent/empty →
    hard error (no `secrets.token_urlsafe` random, no weak default). Re-provision converges to **exactly one
    password = the secret**, so the credential is reproducible and nothing is orphaned (fixes the C-verify
    "unprovisioned" symptom).
  - **Deterministic reset-then-declare.** A single `ACL SETUSER app_<tenant> reset on >{secret} ~ns:* &ns:*
    +@all -@dangerous` — `reset` returns the user to a clean baseline (off, no passwords/keys/channels, `-@all`),
    then the full desired state is declared. Arguments are **discrete RESP tokens** (the secret and patterns are
    never space-joined / re-parsed).
  - **Persist.** `ACL SAVE` after `SETUSER` (`acl_save` default True; `aclfile` = source of truth on restart).
  - **CLI never echoes the secret** — prints username/namespace + a password-masked DSN + a pointer to
    `BASIC_INFRA_REDIS_APP_PASSWORD`; the "not retrievable" caveat is gone.
  - **Prod ownership** (host runbook step, not a code fork; H4): `chown 999:999 redis_shared/acl` + `chmod 750`
    so redis (uid 999) owns the bind-mounted aclfile dir and the `ACL SAVE` temp-file + atomic rename work under
    non-world-writable perms. **Survive-recreate verification** (stop + `rm -f` + recreate `--profile
    redis-shared` → ACL + data persist, writable as 999) is **green-lit separately** — it blips the shared cache.
  - Integration test (exactly one password = secret · namespace scope · re-run idempotency) against a throwaway
    redis is a **follow-up** — no such fixture in the suite yet.

## Consequences
- Gateway recreate / sustained load no longer produces multi-minute hangs: bounded failure + auto-recovery.
  **Unblocks reverting the :8014 eval bypass** (telcoss ADR-0015 / phase H5).
- telcoss runs least-privilege → reduced blast radius.
- Re-provision becomes repeatable → no more orphaned credentials.
- Health-driven reconnect adds backend-client lifecycle complexity, mitigated by graceful swap + deferred
  `aclose()` and covered by the controlled recreate-repro test.
- **H1c finding:** removed the non-canonical `tpro-backend-cpu` container that shadowed `tpro-backend-gpu` on
  the `tpro-backend:8080` network alias (DNS round-robin hazard — masked backend-down, defeated deterministic
  health flips). Canonical stack runs `--profile llm-gpu` only; do not restart the cpu leftover.

## Implementation phases (this ADR)
- **H1** (basic-infra): gateway timeout/limits/config/compose (H1a) + health-driven reconnect (H1b).
- **H2a** (basic-infra): least-priv pg role provisioning.
- **H2b** (basic-infra): redis re-provision idempotency + prod ownership.

Cross-track dependents (telcoss ADR-0015): H3 DSN switch (needs H2a), H4 `/health` green-up
(migrations 0008–0010 by owner + MinIO sidecar + redis secret from H2b), H5 bypass-revert (gated on H1 verified).
