# Runbook — adding a backend

> **Status:** stub. Filled in Phase 8 once the adapter layer (Phase 4) is built.

How to register a new model or a new backend engine in the platform.

Reference: ADR-0005 (backend pluggability).

## Adding a new model to an existing backend kind

1. Add a `models:` entry under the relevant backend in `llm/backends.yaml`.
2. Reload config (`SIGHUP` to the gateway, or restart).
3. Confirm with `GET /v1/models`.

_TODO(week4-phase-8): worked example._

## Adding a new backend kind

1. Implement an adapter under `llm/gateway/app/backends/<kind>.py` satisfying
   the `BackendAdapter` ABC.
2. Register the `kind` in the registry's adapter dispatch table.
3. Add a `backends:` entry in `llm/backends.yaml`.
4. Add the backend service to `docker-compose.yml` under the right profile.

_TODO(week4-phase-8): worked example, health-check expectations, gotchas._
