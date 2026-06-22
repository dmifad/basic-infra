# 0017 — Provisioning-idempotency test strategy (hermetic, never live)

* **Status:** Accepted
* **Date:** 2026-06-23
* **Relates to:** ADR-0016 §2 (least-privilege `app_telcoss` pg role), ADR-0016 §3
  (redis ACL consume-and-reassert); telcoss ADR-0016 (live runtime-hardening guards)

## Context

The control-plane provisioning paths assert a **consume-and-reassert** contract:

* **pg** (`postgres/_local.py::grant_runtime_role`): `CREATE ROLE` is guarded by
  `IF NOT EXISTS`, then `ALTER ROLE … WITH LOGIN NOSUPERUSER NOCREATEDB
  NOCREATEROLE NOBYPASSRLS PASSWORD …` runs **every call**, re-asserting the
  least-privilege attributes (+ the operator password) regardless of prior state.
* **redis** (`redis_shared/local_adapter.py::provision`): a single
  `ACL SETUSER app_<tenant> reset on >{secret} ~ns:* &ns:* +@all -@dangerous` —
  `reset` returns the user to a clean baseline, then the full desired state is
  declared, so re-runs converge to exactly one credential (no accumulation).

These were verified manually in operator windows; there was **no automated
regression coverage**. Existing tests cover only the DB-free guards (e.g.
`provision requires the app-password secret`).

## Decision

1. **Idempotency is regression-guarded with HERMETIC testcontainers — never the
   live shared infra.** Provisioning is a *mutation*: a live run would rotate the
   real `app_telcoss` password and `ALTER`/`reset` the real role/ACL. The guards
   therefore spin throwaway containers (`postgis/postgis:16-3.4`, `redis:7.2-alpine`)
   and never touch postgres-multi `:5434` / redis-shared `:6380`. Marked
   `@pytest.mark.integration`, deselected from `make test`, run via
   `make test-integration`.

2. **H2a — pg role reassert proven by drift-injection.**
   (`test_app_role_reassert_strips_drift_when_reprovisioned`, added to the
   postgres SDK test module, reusing its `postgis_container`): provision twice
   (idempotent); assert the role is least-privilege
   (`rolsuper/rolcreatedb/rolcreaterole/rolbypassrls = false`, `rolcanlogin =
   true`); then **inject drift** (`ALTER ROLE app_telcoss CREATEDB SUPERUSER`),
   re-provision, and assert the drift is **stripped** — the unconditional
   `ALTER ROLE` re-asserts the contract.

3. **H2b — redis single-credential proven by re-provision + GETUSER.**
   (`test_acl_provision_converges_to_single_credential_when_reprovisioned`, new
   file `redis_shared/tests/test_local_provision_idempotency.py`): provision twice
   against an ephemeral redis, then `ACL GETUSER app_telcoss` asserts: user `on`,
   **exactly one** password hash (reset → no accumulation), key scope `~telcoss:*`
   (and nothing broader), channel scope `&telcoss:*`, command categories `+@all`
   and `-@dangerous`. `acl_save` is off for the bare container (no aclfile;
   idempotency is in-memory).

## Consequences

* The two core provisioning guarantees regress-protect ADR-0016 §2/§3 without any
  risk to live tenant credentials.
* `make test-integration` now requires a working container runtime (docker) for
  these two guards; `make test` stays fast and stack-independent.
* redis-py note: `ACL GETUSER` is parsed into a dict where `@`-categories are
  split out of `commands` into a separate `categories` key — the guard binds the
  `+@all`/`-@dangerous` assertion accordingly.
