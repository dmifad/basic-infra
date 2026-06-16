# tracing/ — distributed tracing infra (ADR-0012)

Config-only component (no control-plane CLI, unlike `postgres/`) — Tempo
provisions nothing per-tenant.

```
tracing/
  compose/
    tracing.yml          # Tempo service, profile: ["tracing"], shifted host ports
    tempo/
      tempo.yaml         # Tempo monolithic config (OTLP receivers, local storage)
```

Wired into the root `docker-compose.yml` via `include:` (same mechanism as
`postgres/compose/postgres.yml`). Relative volume paths resolve from repo root —
do NOT prefix with `./`. See `docs/adr/0012-distributed-tracing.md` and
`docs/runbooks/tracing-adoption.md`.

The SDK side lives in `sdk/basic_infra_observability_client` (module
`tracing.py`) — tracing extends the observability client rather than shipping a
separate SDK.
