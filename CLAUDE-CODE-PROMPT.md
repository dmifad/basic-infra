# CLAUDE-CODE-PROMPT — Week 7 (basic-infra observability foundations)

You are operating in `~/basic-infra/` on branch `week7-observability`.
Week 7 introduces an observability stack (Prometheus + Loki + Promtail +
Grafana) and an SDK (`basic_infra_observability_client`). The skeleton
has been unpacked into the working tree by my apply step. Your job is
to land it cleanly into the existing repo.

**Read first, in order:**

1. `CLAUDE.md` — platform invariants (updated for Week 7). **Do not violate them.**
2. `docs/architecture/bridge-v12.md` — full ecosystem state after Week 6 commit.
3. `docs/adr/0011-observability-foundations.md` — the decision you are landing.
4. `docs/runbooks/observability-operations.md` — operational procedures.

**Important context from bridge-v12 (read carefully):**

- ADR-0009, `migrate-to-basic-infra` branch, and compliance/extraction gate
  belong to **`~/telcoss/`**, not this repo. They do **not** block anything here.
  Treat any reference to them in bridge-v12 as informational only.
- The Week 6 storage layer is committed on `week6-storage-layer @ 7b878a6`,
  not merged. Week 7 builds on that. Do NOT merge week6-storage-layer
  during this session — it's a parallel branch ready for separate review.
- `stash@{0}` holds pre-Week6 llm/ tweaks. **Do not pop it.**

**Hard rules for this session:**

- Do not commit anything. Do not push. Leave working copy ready for my review.
- Do not modify `llm/` (frozen platform contract).
- Do not modify `storage/` or `sdk/basic_infra_storage_client/` (frozen
  after Week 6 commit).
- Do not modify `telcoss/*` (different repo).
- If something looks ambiguous (existing CLAUDE.md, compose topology,
  test conventions) — **stop and ask me**, do not guess.

**Pre-flight check before Phase 0:**

Look at git status. If you see Week 6 storage files as untracked or modified,
that means you're on `main` or another branch where Week 6 is not present.
**Stop and report.** Week 7 must branch from `week6-storage-layer` (so that
the observability layer can be developed knowing storage exists), not from `main`.

---

## Phases

Execute strictly in order. Phases marked `/goal-friendly` can be batched
under one `/goal` invocation. Phases marked `manual` require pausing for my
review or explicit go-ahead.

### Phase 0 — Reconcile CLAUDE.md (manual)

If `CLAUDE.md.before-week7` exists in the repo root (left by my apply step):

- Diff it against the new `CLAUDE.md`.
- If the old file has content not covered by the new one — propose a
  merged version, show me the diff, **wait for my approval**.
- If the old file is fully covered by the new one — delete the backup.

If no `CLAUDE.md.before-week7` exists, skip this phase.

### Phase 1 — Inventory (manual)

Print:

- `git rev-parse --abbrev-ref HEAD` — current branch (must be `week7-observability`).
- `git log --oneline -3` — top three commits (Week 6 commit `7b878a6` should
  be in the history).
- `git status --short`.
- `find observability sdk/basic_infra_observability_client -type f | sort` —
  what was unpacked.
- Current `pyproject.toml` (or equivalent) location and format. NOTE: as of
  Week 7 there is **no root pyproject.toml** — only per-SDK ones. This is the
  root-config gap closed in Phase 1a.
- Existing `Makefile` — print its current targets (basic-infra already has a
  Makefile; you will EXTEND it, not replace it).
- Existing `.venv/` — present from Week 6 but populated ad-hoc via pip. Print
  `.venv/bin/python --version` and `pip list | grep -E "pytest|asyncio|moto"`
  to see what's already installed.
- Current `docker-compose.yml` top-level: services list, any `include:`
  directives. Confirm that Week 6's `storage/compose/minio.yml` is in
  the include list (sanity check that Week 6 landing was clean).
- Current test runner config, markers convention.
- Current linter/formatter config.

Stop. Show me the inventory. **Wait for my "go" before Phase 1a.**

### Phase 1a — Root dev-environment housekeeping (manual)

**Why first:** the repo has no root dev-env or test-runner config. A bare
`pytest storage/ sdk/...` fails with `ModuleNotFoundError: pytest_asyncio`
when run with the system python, and the integration marker only registers
when an SDK pyproject is the active configfile (PytestUnknownMarkWarning).
Week 6 worked around this with a throwaway `.venv` + `PYTHONPATH=` prefixes.
Phase 4 (and Week 7's own tests) need this fixed first. This is the
housekeeping flagged in bridge-v12.

Do, basing concrete choices on the Phase 1 inventory:

1. **Root dependency manifest.** Create a root `pyproject.toml` (preferred) or
   `requirements-dev.txt` — match whatever convention `llm/` uses if it has one.
   Declare dev deps: `pytest`, `pytest-asyncio`, `aiobotocore`, `aiofiles`,
   `pydantic`, `pydantic-settings`, `moto[s3]`, `structlog`, `prometheus-client`,
   `ruff`, `mypy`. (Runtime deps for storage + observability also belong here
   or in component extras — your call based on inventory, but state it.)
2. **Root pytest config.** `[tool.pytest.ini_options]` in root pyproject (or
   `pytest.ini`): `asyncio_mode = "auto"`, `testpaths` covering `storage/tests`
   and the two SDK `tests/` dirs, registered `markers = ["integration: ..."]`
   so the warning disappears.
3. **Import resolution without PYTHONPATH.** Set `pythonpath = [".", "sdk/basic_infra_storage_client", "sdk/basic_infra_observability_client"]`
   in the pytest config (pytest 7+ supports this), OR adopt a src-layout —
   whichever fits the repo. Goal: `pytest` from repo root resolves `storage.*`
   and both SDK packages with no `PYTHONPATH=` prefix.
4. **Reuse the existing `.venv`.** Don't recreate it. Install the root dev
   manifest into it (`.venv/bin/pip install -e ".[dev]"` or
   `-r requirements-dev.txt`). Confirm `.venv/bin/pytest` is on path.
5. **Extend the existing `Makefile`** (do not overwrite). Add/repair targets:
   `make test` (storage + both SDKs + observability, no PYTHONPATH),
   `make test-integration` (`-m integration`), `make lint` (ruff over
   `storage/ sdk/ observability/`), `make typecheck` (mypy same scope).
   Mirror the style of telcoss's Makefile if useful as reference, but this is
   basic-infra's own.

**Show me the proposed root pyproject.toml + Makefile diff before applying.**

After applying, verify the gap is closed:

```bash
make test        # storage 25 tests green, no PYTHONPATH, no marker warning
```

(observability's 15 join once Phase 4 runs — but the runner must already work.)

### Phase 2 — Dependency wiring (/goal-friendly)

Fold the observability SDK dependencies into the root manifest created in
Phase 1a (not a separate place):

- `structlog>=24.1`
- `prometheus-client>=0.20`
- `pydantic-settings>=2.2` (already present from Week 6 — verify)
- `pydantic>=2.6` (already present — verify)

Match the dep declaration style established in Phase 1a.

### Phase 3 — Lint / typecheck (/goal-friendly)

Run via the Makefile targets added in Phase 1a:

```bash
make lint        # ruff over storage/ sdk/ observability/
make typecheck   # mypy same scope (if mypy configured)
```

Fix violations. If a fix would change semantics (not just style) — flag
it and ask before applying.

### Phase 4 — Tests green (/goal-friendly)

With the Phase 1a root config in place, run via Makefile (no PYTHONPATH):

```bash
make test
```

Expected: observability 15 + storage 17 + storage SDK 3 = 35 passed,
no `PytestUnknownMarkWarning`. Integration (moto) separately:

```bash
make test-integration
```

Expected: 8 moto S3 tests passed (Week 6). If `make test` still needs a
PYTHONPATH prefix or emits the marker warning, Phase 1a is incomplete —
go back and fix the root config, don't work around it here.

### Phase 5 — Config validation (/goal-friendly)

Validate the observability config files (do NOT start containers yet):

- YAML syntax:
  ```bash
  python -c "import yaml; yaml.safe_load(open('observability/prometheus/prometheus.yml'))"
  python -c "import yaml; yaml.safe_load(open('observability/loki/loki.yml'))"
  python -c "import yaml; yaml.safe_load(open('observability/promtail/promtail.yml'))"
  python -c "import yaml; yaml.safe_load(open('observability/grafana/provisioning/datasources/datasources.yml'))"
  python -c "import yaml; yaml.safe_load(open('observability/grafana/provisioning/dashboards/dashboards.yml'))"
  ```
- Compose validation:
  ```bash
  docker compose -f observability/compose/observability.yml config -q
  ```
- Dashboard JSON:
  ```bash
  python -c "import json; json.load(open('observability/grafana/dashboards/basic-infra-overview.json'))"
  ```

All should pass without errors.

**Cross-check against archived v1.** The previous Week 7 attempt is preserved
at tag `week7-v1-archived` (commit `eabf121`). It contained empirically-found
fixes. Two are already folded into this v2 package:

- bind-mount paths use `../` (relative to `observability/compose/`), not `./observability/`
- `external_labels.env` dropped from `prometheus.yml` (env comes via SDK labels)

Verify both are present in the working tree, and diff the v1 observability
files against v2 to confirm no *other* v1 fix was lost:

```bash
git show week7-v1-archived:observability/compose/observability.yml > /tmp/v1-obs.yml
diff /tmp/v1-obs.yml observability/compose/observability.yml
# Expected differences: ports (v1 9090/3100/3000 → v2 9190/3110/3002),
# loopback bind (v2 adds 127.0.0.1). Anything else — investigate before proceeding.
```

If the diff shows a v1 fix not in v2 beyond ports/loopback — flag it, don't
silently drop it.

### Phase 6 — Compose integration (manual)

Wire `observability/compose/observability.yml` into the project's compose
topology (mirror what was done for `storage/compose/minio.yml` in Week 6).

- If the top-level `docker-compose.yml` uses `include:` — add observability.
- Add observability env block to `.env.example`:

  ```
  # Observability (Week 7)
  PROMETHEUS_PORT=9190
  LOKI_PORT=3110
  GRAFANA_PORT=3002
  GRAFANA_ADMIN_USER=admin
  GRAFANA_ADMIN_PASSWORD=admin
  BASIC_INFRA_OBSERVABILITY_SERVICE_NAME=basic-infra
  BASIC_INFRA_OBSERVABILITY_ENV=dev
  BASIC_INFRA_OBSERVABILITY_LOG_FORMAT=json
  ```

**Show me the proposed `docker-compose.yml` change before applying.**

Do not start the stack yet.

### Phase 7 — Live stack smoke (manual, optional)

Only if I explicitly say "do the smoke".

```bash
docker compose --profile observability up -d
docker compose ps prometheus loki promtail grafana
```

Wait for all four to be healthy (`Loki` takes the longest, ~30s).

Verify:

- `curl -fsS http://localhost:9190/-/healthy` → 200
- `curl -fsS http://localhost:3110/ready` → 200
- `curl -fsS http://localhost:3002/api/health` → 200
- `curl -s http://localhost:9190/api/v1/targets | jq '.data.activeTargets[].labels.job'`
  → list of jobs including `prometheus`, `loki`, `grafana`, `promtail`.

Then write a one-shot Python script that:

- Calls `setup_logging(ObservabilitySettings(service_name="smoke-test", env="dev"))`
- Calls `setup_metrics(...)` on port 9091
- Increments a test counter
- Sleeps long enough for Prometheus to scrape (~30s)
- Queries `http://localhost:9190/api/v1/query?query=smoke_test_*`
- Asserts the metric is present

Tear down: `docker compose --profile observability down`.

### Phase 8 — Review prep (manual)

- Print `git diff --stat` — summary of changes.
- Print full diff for `docker-compose.yml`, `.env.example`, and any other
  cross-cutting files you touched.
- Print TODO list: anything you decided to defer, anything that needs my
  attention, any rough edges.
- **Do not commit. Stop.**

---

## Reference

- ADR-0011 — `docs/adr/0011-observability-foundations.md`
- Operations runbook — `docs/runbooks/observability-operations.md`
- Ecosystem bridge — `docs/architecture/bridge-v12.md`
- Slash commands — `.claude/commands/verify-observability.md`,
  `.claude/commands/observability-status.md`
- Tasklist (this session) — `tasklist.md`
