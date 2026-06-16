# Runbook — distributed tracing adoption (Tempo + OTEL)

ADR-0012. How to stand Tempo up in basic-infra and adopt tracing in a client
project (telcoss in Week 11).

## 1. Host prep (one-time, vams-dev)

Tempo's official image runs as uid/gid `10001`. The HDD bind dir must exist and
be owned by it, or Tempo fails to write WAL/blocks.

```bash
sudo mkdir -p /mnt/HDD/telcoss/tempo
sudo chown -R 10001:10001 /mnt/HDD/telcoss/tempo
```

## 2. Bring Tempo up

Tempo's Grafana datasource only resolves when the Week 7 Grafana
(`observability` profile) is also running. Use the combined target:

```bash
make up-observability-full     # observability + tracing profiles
# or explicitly:
docker compose --profile observability --profile tracing up -d
```

Tempo alone (no datasource) — naming the service enables its profile implicitly:

```bash
make up-tracing                # docker compose up -d tempo
```

Verify:

```bash
curl -s http://127.0.0.1:3210/ready          # -> "ready"
docker compose config --services | grep -q '^tempo$' && echo "LEAK: profile-less" || echo "ok: gated"
docker compose --profile tracing config --services | grep tempo   # must list tempo
```

Tear down only Tempo (NEVER `docker compose down tempo` — on Compose 5.x that
tears down the whole project; see Week 8 lesson):

```bash
make down-tracing              # stop + rm -f tempo
```

## 3. Adopt in a client project (FastAPI + SQLAlchemy)

### 3.1 Dependency (path dep with the `tracing` extra)

```toml
[tool.poetry.dependencies]
basic_infra_observability_client = { path = "../basic-infra/sdk/basic_infra_observability_client", develop = true, extras = ["tracing"] }
```

```bash
poetry install
```

### 3.2 Environment

```bash
BASIC_INFRA_OBSERVABILITY_TRACING_ENABLED=true
BASIC_INFRA_OBSERVABILITY_TRACING_SERVICE_NAME=telcoss-api
BASIC_INFRA_OBSERVABILITY_TRACING_ENV=staging        # explicit; not the app ENV
BASIC_INFRA_OBSERVABILITY_TRACING_OTLP_ENDPOINT=http://tempo:4317
BASIC_INFRA_OBSERVABILITY_TRACING_SAMPLE_RATIO=1.0
```

Disabled (`…_ENABLED=false`, the default) makes every call below a no-op — safe
to ship before Tempo is reachable.

### 3.3 Wire-up at app startup

```python
from basic_infra_observability_client.tracing import (
    setup_tracing, instrument_sqlalchemy, install_trace_log_correlation,
)

def build_app() -> FastAPI:
    app = FastAPI()
    setup_tracing(app=app)                 # configures provider + instruments FastAPI
    install_trace_log_correlation()        # trace_id/span_id into log records
    return app

# For the async engine, instrument the underlying sync engine:
instrument_sqlalchemy(async_engine.sync_engine)
```

The service must share the `basic-infra-net` network so `tempo:4317` resolves.

### 3.4 Loki ↔ Tempo correlation

The Tempo datasource provisions `tracesToLogsV2 → Loki` (trace → its logs). The
reverse (log line → trace) needs a **derived field** on the Loki datasource that
extracts `trace_id` from the JSON log line and links to the Tempo datasource.
This is **already provisioned** in `datasources.yml` (the Week-7 Loki datasource);
the snippet below is what ships:

```yaml
# observability/grafana/provisioning/datasources/datasources.yml  (Loki datasource)
jsonData:
  derivedFields:
    - name: TraceID
      # regex matcher against the JSON log body. \s* is load-bearing: structlog's
      # JSONRenderer emits `"trace_id": "<hex>"` WITH a space after the colon —
      # a no-space regex silently never matches.
      matcherRegex: '"trace_id":\s*"(\w+)"'
      url: "$${__value.raw}"
      datasourceUid: tempo
```

The `trace_id` is emitted primarily by the structlog processor
`logging_setup._add_trace_context` (the SDK logs through structlog);
`tracing.TraceContextFilter` is the stdlib-logging fallback for code that bypasses
structlog. Both write the same `trace_id` key.

> Verify the real Loki datasource `uid` matches `tracesToLogsV2.datasourceUid`
> in `tempo.yml` (both are pinned: `uid: loki` / `datasourceUid: loki`).
> Mismatched uids break correlation silently.

## 4. Verify a trace end-to-end

1. Hit a client endpoint.
2. Grafana → Explore → Tempo → search by service `telcoss-api` → open a trace.
3. From a span, "Logs for this span" → should land in Loki filtered by trace_id.
4. From a Loki log line with `trace_id`, the derived field links back to Tempo.

## 5. Deferred (see ADR-0012 + bridge §5)

- metrics_generator / service-graph (needs Prometheus remote-write — touches the
  Week 7 Prometheus contract; out of v1 scope).
- Per-route / tail sampling.
- Object-store backend (MinIO/S3) swap when retention/volume demands it.

## 6. Week 11 cutover note

At cutover the Tempo host ports flip from shifted (3210/4417/4418) to canonical
(3200/4317/4318) together with the rest of the observability stack. In-network
clients are unaffected — they already use `tempo:4317`.
