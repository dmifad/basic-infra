# ADR-0012 — Distributed tracing (OpenTelemetry + Tempo)

- **Status:** Accepted
- **Date:** 2026-06-04
- **Track:** Platform (basic-infra), Week 7+
- **Supersedes / relates to:** extends ADR-0011 (observability foundations);
  follows the SDK + profile pattern of ADR-0013 (postgres-multi).
- **Reserved number:** 0012 was held for tracing across bridges v13/v14.

## Context

basic-infra already ships metrics (Prometheus) and structured logs
(Loki/Promtail) through `basic_infra_observability_client` (ADR-0011), which
already carries a `request_id`. The missing third signal is distributed traces.
Client projects (telcoss first, Week 11) are FastAPI + SQLAlchemy 2.x async over
PostgreSQL/Redis; a request crosses several layers and we currently cannot follow
one request end-to-end nor correlate a log line to the span that produced it.

Constraints carried into this decision:
- **replace-not-coexist**, **profile-gated**, **shifted loopback ports** — the
  same discipline used for observability and postgres-multi. A new infra service
  must not auto-start on a bare `docker compose up` and its host ports must not
  collide with telcoss or existing basic-infra ports until Week 11 cutover.
- **ENV split stays explicit** (ADR-0011 §Config): the deployment-env field is
  read from a dedicated prefixed var, never unified with the app `ENV` via
  `AliasChoices`.
- The Week 7 Prometheus contract must remain untouched.

## Decision

1. **Backend: Grafana Tempo**, single-binary (monolithic) mode, local block
   storage on the HDD tier (`/mnt/HDD/telcoss/tempo`, alongside Loki). OTLP
   receivers for gRPC (4317) and HTTP (4318) inside the compose network.

2. **Extend `basic_infra_observability_client` — no separate SDK.** Tracing
   lives in a new `tracing` module of the existing observability client. Reasons:
   the client already owns `request_id`; keeping metrics + logs + traces in one
   surface lets us correlate all three (a single `setup_observability`-style call
   site, shared resource attributes, one env-prefix family). A separate
   `basic_infra_tracing_client` would fragment that correlation and double the
   adoption surface in Week 11. OTEL instrumentation libs are **optional extras**
   so the core SDK does not pull FastAPI/SQLAlchemy into projects that do not use
   them.

3. **Config under the observability env family**, prefix
   `BASIC_INFRA_OBSERVABILITY_TRACING_`:
   `…_ENABLED` (default `false` — adoption is gradual, disabled = no-op),
   `…_SERVICE_NAME`, `…_SERVICE_VERSION`, `…_ENV` (the explicit deployment-env,
   **not** aliased to app `ENV`), `…_OTLP_ENDPOINT` (default `http://tempo:4317`),
   `…_OTLP_INSECURE` (default `true` on the in-cluster network), `…_SAMPLE_RATIO`
   (default `1.0`, `ParentBased` sampler).

4. **Correlation glue:** a `TraceContextFilter` injects `trace_id`/`span_id`
   into log records so logs shipped to Loki link back to Tempo spans; the Grafana
   Tempo datasource adds `tracesToLogsV2 → Loki` for the reverse jump. Both
   directions are wired in provisioning.

5. **Profile `tracing`, shifted host ports** (loopback-only): Tempo HTTP
   `3210`, OTLP gRPC `4417`, OTLP HTTP `4418`. In-network clients use the
   canonical container ports (`tempo:4317`); the shifted ports are host-side
   debug only. At **Week 11 cutover** the host ports flip to canonical along with
   the rest of the observability stack.

## Coexistence (host loopback ports, pre-Week-11)

| Service | Component | Host port | Profile |
|---|---|---|---|
| basic-infra | Prometheus | 9190 | observability |
| basic-infra | Loki | 3110 | observability |
| basic-infra | Grafana | 3002 | observability |
| basic-infra | MinIO (S3 / console) | per ADR-0010 | minio |
| basic-infra | PostgreSQL (postgres-multi) | 5434 | postgres |
| **basic-infra** | **Tempo HTTP API** | **3210** | **tracing** |
| **basic-infra** | **Tempo OTLP gRPC** | **4417** | **tracing** |
| **basic-infra** | **Tempo OTLP HTTP** | **4418** | **tracing** |
| telcoss | PostgreSQL | 5433 | — |
| basic-infra | LLM gateway | 8013 | — |

## Consequences

Positive:
- End-to-end request traces; one-click log↔trace navigation in Grafana.
- Single observability adoption surface for telcoss in Week 11.
- Local backend keeps v1 cheap; Tempo is object-store-ready (MinIO/S3) when
  retention or volume demand it — a config swap, no code change.

Costs / follow-ups (deferred, tracked in bridge §5):
- **metrics_generator / service-graph is OFF in v1.** Enabling it requires
  Prometheus `remote-write` receiver, which touches the Week 7 Prometheus
  contract — deliberately deferred so this change stays additive. `serviceMap`
  datasource wiring is pre-staged but inert until then.
- Sampling is global ratio only; per-route / tail sampling is future work.
- OTLP exporter pulls `grpcio` into the SDK closure.

## Alternatives considered

- **Jaeger** instead of Tempo: rejected — Tempo is Grafana-native (reuses the
  Week 7 Grafana, no second UI), shares the Loki-style local→object-store
  storage model, and needs no separate index store.
- **Separate `basic_infra_tracing_client` SDK**: rejected — fragments
  metric/log/trace correlation and doubles Week 11 adoption work (see Decision 2).
- **Unify `…_TRACING_ENV` with app `ENV`**: rejected — violates the ADR-0011
  ENV-split discipline.
