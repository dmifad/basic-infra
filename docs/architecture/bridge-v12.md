# Personal ecosystem — bridge v12

**Snapshot date:** 2026-05-24
**Last completed:** Week 6 (`7b878a6` on `week6-storage-layer`, not merged)
**Next target:** Week 7 — basic-infra observability foundations (metrics + logs + Grafana + SDK)

This bridge replaces v11. v11 was written before Week 6 landed and before
the strategic ordering (platform → applied → quality) was made explicit.

---

## 1. Ecosystem state

Three repos:

| Repo | Last commit | Notes |
|---|---|---|
| `~/basic-infra/` | `7b878a6` on `week6-storage-layer` | Storage layer landed. **Not merged.** |
| `~/telcoss/` | Week 5 + `reviewer-task-followup` (unchanged since v11) | Compliance BC structurally complete, gate OPEN. |
| `~/PAMYAT-NARODA-GRAPH/` | Week 4 phase 6 (unchanged since v11) | Paused. LLM services out of compose. |

Branches:

| Repo | Branch | State |
|---|---|---|
| basic-infra | `main` | pre-Week-6 |
| basic-infra | `week6-storage-layer` | `7b878a6`, +1 ahead of base, ready for review |
| basic-infra | `stash@{0}` | "llm: pending reviewer-task tweaks (pre-Week6)" — three llm/* files |
| telcoss | `main` | Week 2 |
| telcoss | `migrate-to-basic-infra` | Weeks 3+4+5 unmerged, gate OPEN |
| telcoss | `reviewer-task-followup` | 4 ahead of `migrate-to-basic-infra` |

---

## 2. What's incrementally new since v11

### Week 6 done — basic-infra storage layer (`7b878a6`)

- `BlobStorePort` + three adapters (`FilesystemAdapter`, `MinioAdapter`, `S3Adapter`)
- `basic_infra_storage_client` SDK (async + sync, tenant-scoped)
- MinIO compose profile (`storage/compose/minio.yml`) wired via top-level `include:`
- Storage env block in `.env.example`
- ADR-0010 (storage abstraction)
- pdf-intake storage migration runbook (7 phases, fs → blob store, non-breaking)
- 25 tests passing: 17 unit + 8 moto integration

### Disambiguation lessons learned (carried into future prompts)

- **ADR-0009 lives in `~/telcoss/`**, NOT `~/basic-infra/`. It is compliance-extraction
  domain, not platform. Future basic-infra session prompts must not block on it.
- **`migrate-to-basic-infra` is a `~/telcoss/` branch**, not basic-infra. It's
  the telcoss-side migration onto the platform.
- **basic-infra compose network is `basic-infra-net`** (not `basic-infra`).
- **`_s3_compatible.py.get()` has a known client-lifecycle compromise** — the
  client is held open for the duration of body streaming. Documented `NOTE`
  in code, deferred fix bundled with pdf-intake adoption (Week 10).
- **telcoss already runs a full observability stack** —
  `~/telcoss/infra/compose/compose.observability.yml`: Prometheus (host 9090),
  Grafana (3001), Loki (3100), Promtail, redis-exporter, postgres-exporter.
  It is NOT part of the normal telcoss dev cycle (`make dev`/`make up` exclude
  it; only `make up-observability` brings it up). The Week 7 platform stack
  **replaces** it — see §5. All telcoss host-ports bind to `127.0.0.1`.
- **Compose `include:` resolves relative bind-mount paths against the included
  file's own directory**, not the repo root. A profile at
  `observability/compose/observability.yml` mounting `observability/prometheus/...`
  must use `../prometheus/...`, not `./observability/prometheus/...`. Week 6's
  `storage/compose/minio.yml` didn't hit this (named volumes, no config
  bind-mounts). Future profiles with bind-mounted config (postgres-multi,
  redis-shared) must use `../`-relative paths. (Discovered in the archived
  Week 7 v1 commit; re-applied to v2.)

---

## 3. Strategic ordering — agreed sequence

Confirmed direction:

1. **Платформенный (basic-infra) — exhaustive first.**
   - Week 7 = observability foundations (this session)
   - Week 7+ = distributed tracing (OTEL + Tempo) — separate iteration
   - Week 8 = postgres-multi
   - Week 9 = redis-shared
2. **Прикладной (telcoss) — after platform layers settle.**
   - Week 10 = pdf-intake adoption (storage migration phase 1) + `_s3_compatible.py.get()` lifecycle refactor
   - Week 11 = observability SDK adoption across telcoss services + cutover (remove telcoss observability stack, flip platform stack to canonical ports)
   - Week 12 = postgres-multi + redis-shared adoption
3. **Качественный (telcoss) — final track.**
   - Compliance prompt iteration v3+ in focused sessions until pass rate ≥80%
   - Close ADR-0009 gate
   - Merge `migrate-to-basic-infra → main` in telcoss
   - At this point both `main`s (basic-infra and telcoss) reflect production reality.

Quality-track can run in parallel with platform sessions in shorter focused
slots — it doesn't block platform work, and platform work doesn't block it.
Strictly sequential ordering is for **applied** track (must wait for platform
slabs to be available before adopting them).

---

## 4. Open threads — explicit deferral list

Carried from v11:

- M&A watermark deviation from ADR-0007
- M&A namespace merge stubbed
- Reconciliation drift detection batch-only
- Anthropic adapter in basic-infra — stub only

**Five compliance follow-ups** (carried from v11 §5):

1. Prompt iteration v3+ — quality track
2. `compliance.regulatory_requirements.clause_article` varchar(64) overflow
3. `failed_extractions` table for post-hoc analysis
4. Production-model decision (T-pro 72B not viable; Qwen 7B vs cloud routing)
5. Per-document-kind LLM provider routing (ADR-0011 in telcoss, OR extension of ADR-0009)

**Week 6 specific (new):**

- `_s3_compatible.py.get()` client lifecycle refactor — Week 10 (bundled with adoption)
- Root pytest/mypy/Makefile config — Week 7 Phase 1a housekeeping (no root pyproject; .venv populated ad-hoc; bare pytest fails on pytest_asyncio)
- llm/ pre-Week6 tweaks in `stash@{0}` — separate session/PR, not Week 7 scope

---

## 5. Week 7 scope — basic-infra observability foundations

Work in `~/basic-infra/`. Three pieces:

- **Metrics:** Prometheus + scrape configuration + standard exporters posture
  (services expose `/metrics`; no host-level exporters this week).
- **Logs:** Loki + Promtail. JSON structured logs from `structlog` (already in
  codebase vocabulary) shipped via Promtail.
- **Visualization:** Grafana with provisioned datasources and one base
  dashboard. Dashboards as code (JSON in `observability/grafana/dashboards/`).

Plus an SDK — `basic_infra_observability_client` — that gives client projects:

- `setup_logging(service_name, env)` — one-line structlog → JSON config
- `metrics.counter / histogram / gauge` — prometheus_client helpers with consistent label conventions
- `metrics.serve(port=9090)` — start the `/metrics` HTTP endpoint
- `context.request_id` — contextvar with bind/get/with-scope helpers
- Adoption pattern matches `basic_infra_storage_client`.

**Deliberately out of scope (deferred):**

- Distributed tracing (OTEL + Tempo/Jaeger). Requires service-side instrumentation;
  separate week, separate ADR (0012).
- HA / multi-instance observability stack. Single instance per environment for now.
- Alerting (Alertmanager / Loki rules). Once dashboards exist and adoption proves out
  signal-to-noise, separate week.
- Service-side instrumentation. Adoption happens in applied track sessions, per service.
- cAdvisor / node-exporter. Add only when a concrete debug question demands them.

### The decision recorded in this bridge

Week 7 produces the **platform stack and SDK**, not adoption. After Week 7
ends, observability infrastructure is available but no service emits to it
yet. Adoption happens deliberately, per service, during the applied track.

This separation is the same pattern Week 6 used (storage SDK landed Week 6,
adoption is Week 10).

**Replace, not coexist.** The platform stack replaces telcoss's own
observability (which is a full Prometheus/Grafana/Loki/Promtail +
exporters stack today). To let both run on `vams-dev` during the
transition, the platform stack publishes on **shifted, loopback-bound
host-ports**:

| Service | telcoss (existing) | basic-infra (transitional) | after cutover (Week 11) |
|---|---|---|---|
| Prometheus | 9090 | **9190** | 9090 |
| Loki | 3100 | **3110** | 3100 |
| Grafana | 3001 | **3002** | 3000 |

Container-internal ports are unchanged (9090/3100/3000 inside
`basic-infra-net`); only host publication is shifted. Cutover in Week 11
removes telcoss `compose.observability.yml`, repoints exporters/logs to the
platform stack, and flips the platform stack to the canonical ports via
`.env`.

---

## 6. Roadmap (revised)

| Week | Target | Status |
|---|---|---|
| 5 | Telcoss Compliance BC (gate OPEN) | ✓ |
| 6 | basic-infra storage layer | ✓ (`7b878a6`, not merged) |
| **7** | **basic-infra observability foundations** | ← this session |
| 7+ | basic-infra distributed tracing | planned |
| 8 | basic-infra postgres-multi | planned |
| 9 | basic-infra redis-shared | planned |
| 10 | telcoss pdf-intake adoption + storage lifecycle fix | planned |
| 11 | telcoss observability adoption + **cutover** (remove telcoss stack, flip platform stack to canonical ports) | planned |
| 12 | telcoss postgres-multi/redis-shared adoption | planned |
| Parallel | telcoss compliance prompt iteration v3+ → close gate → merge `migrate-to-basic-infra → main` | ongoing |
| Future | MCP server wrapping basic-infra | unscheduled |

---

## 7. How to use this bridge

Open the next session with:

> Personal ecosystem continues. Bridge v12 attached.
> State: Week 6 committed on basic-infra `week6-storage-layer` @ `7b878a6`,
>   not merged. llm/ stash held.
> Today: Week 7 = basic-infra observability foundations
>   (metrics + logs + Grafana + SDK helpers).
> Tracing, alerting, HA, and service-side instrumentation deliberately deferred.
> Constraints: don't break LLM contract, don't break storage SDK,
>   don't touch llm/ stash, don't commit/push, root housekeeping first.

Files worth re-attaching for Week 7:

- `~/basic-infra/docs/adr/0010-storage-abstraction.md` (SDK pattern precedent)
- `~/basic-infra/docs/adr/0001-platform-charter.md` (scope discipline)
- `~/basic-infra/docker-compose.yml` (current topology with `storage/compose/minio.yml` included)

---

## 8. What this bridge intentionally does NOT include

- Week 6 commit content breakdown — see `git show 7b878a6`
- LLM platform internals — see `~/basic-infra/llm/`
- Compliance prompt v1↔v2 diff — see telcoss commit `c350989`
- pdf-intake migration phases 2-7 — see migration runbook in basic-infra

---

**End of bridge v12.** ~3 page read.
