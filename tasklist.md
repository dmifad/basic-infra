# Tasklist — Week 7 (basic-infra observability foundations)

Sequential phases. `/goal-friendly` phases can be batched under one `/goal`
invocation; `manual` phases require my review/approval before proceeding.

---

## Phase 0 — Reconcile CLAUDE.md (manual)

- [ ] Check if `CLAUDE.md.before-week7` exists
- [ ] If yes — diff against new `CLAUDE.md`, propose merge, wait for approval
- [ ] If no — skip

## Phase 1 — Inventory (manual)

- [ ] `git rev-parse --abbrev-ref HEAD` — must be `week7-observability`
- [ ] `git log --oneline -3` — Week 6 commit `7b878a6` in history
- [ ] `git status --short`
- [ ] `find observability sdk/basic_infra_observability_client -type f | sort`
- [ ] Confirm NO root `pyproject.toml` yet (the gap); locate per-SDK ones
- [ ] Print existing `Makefile` targets (will extend, not replace)
- [ ] Inspect existing `.venv/`: python version + `pip list | grep -E "pytest|asyncio|moto"`
- [ ] Verify Week 6 `storage/compose/minio.yml` is in top-level `docker-compose.yml` include list
- [ ] Identify test runner, marker conventions, linter config
- [ ] **Pause for "go".**

## Phase 1a — Root dev-environment housekeeping (manual)

- [ ] Create root dependency manifest (root `pyproject.toml` or `requirements-dev.txt`)
      with dev deps: pytest, pytest-asyncio, aiobotocore, aiofiles, pydantic,
      pydantic-settings, moto[s3], structlog, prometheus-client, ruff, mypy
- [ ] Root pytest config: `asyncio_mode=auto`, `testpaths`, registered `markers`
- [ ] `pythonpath=` in pytest config (or src-layout) — no more PYTHONPATH prefixes
- [ ] Install root manifest into existing `.venv` (don't recreate)
- [ ] Extend existing `Makefile`: `make test`, `make test-integration`, `make lint`, `make typecheck`
- [ ] **Show me root pyproject + Makefile diff. Wait for approval.**
- [ ] Verify: `make test` → storage 25 green, no PYTHONPATH, no marker warning

## Phase 2 — Dependency wiring (/goal-friendly)

- [ ] Fold `structlog>=24.1` into root manifest (from Phase 1a)
- [ ] Fold `prometheus-client>=0.20` into root manifest
- [ ] Verify `pydantic-settings>=2.2` present (from Week 6)
- [ ] Verify `pydantic>=2.6` present

## Phase 3 — Lint / typecheck (/goal-friendly)

- [ ] `make lint` — ruff over storage/ sdk/ observability/
- [ ] `make typecheck` — mypy same scope (if configured)
- [ ] Apply style fixes
- [ ] Flag semantic-changing fixes for review

## Phase 4 — Tests green (/goal-friendly)

- [ ] `make test` — observability 15 + storage 17 + storage SDK 3 = 35 passed, no PYTHONPATH, no marker warning
- [ ] `make test-integration` — 8 moto S3 tests passed (Week 6)
- [ ] If make test still needs PYTHONPATH or warns on markers → Phase 1a incomplete, fix root config
- [ ] Diagnose any failures, do not paper over

## Phase 5 — Config validation (/goal-friendly)

- [ ] YAML syntax for prometheus.yml, loki.yml, promtail.yml
- [ ] YAML syntax for grafana provisioning files
- [ ] `docker compose -f observability/compose/observability.yml config -q`
- [ ] JSON syntax for dashboards/basic-infra-overview.json

## Phase 6 — Compose integration (manual)

- [ ] Determine compose topology (matches Week 6's include pattern)
- [ ] Propose wiring for `observability/compose/observability.yml`
- [ ] **Show me proposed change. Wait for approval.**
- [ ] Apply approved wiring
- [ ] Add observability env block to `.env.example`

## Phase 7 — Live stack smoke (manual, optional)

- [ ] **Only if I say "do the smoke".**
- [ ] `docker compose --profile observability up -d`
- [ ] All four services healthy
- [ ] HTTP healthchecks: Prometheus, Loki, Grafana
- [ ] Targets list includes all four scrape jobs
- [ ] Python smoke: setup → metric increment → Prometheus query → assert present
- [ ] `docker compose --profile observability down`

## Phase 8 — Review prep (manual)

- [ ] `git diff --stat`
- [ ] Full diff for `docker-compose.yml`, `.env.example`, cross-cutting files
- [ ] TODO list of deferred items / open questions / rough edges
- [ ] **Do NOT commit. Stop. Hand off for review.**

---

## Don't list

- [ ] **Don't** touch `llm/` (frozen platform contract)
- [ ] **Don't** touch `storage/` or `sdk/basic_infra_storage_client/` (frozen after Week 6)
- [ ] **Don't** pop `stash@{0}` (pre-Week6 llm/ tweaks, separate session)
- [ ] **Don't** touch `telcoss/*` (different repo)
- [ ] **Don't** merge `week6-storage-layer` anywhere
- [ ] **Don't** commit or push
- [ ] **Don't** start alerting / OTEL tracing (out of scope)
- [ ] **Don't** treat ADR-0009 / migrate-to-basic-infra / compliance gate as blocking — they're in telcoss
