# CLAUDE-CODE-PROMPT — Week 6 (basic-infra storage layer)

You are operating in `~/basic-infra/` on branch `week6-storage-layer`.
Week 6 introduces a storage layer (BlobStorePort + MinIO/S3/filesystem
adapters + SDK). The skeleton has been unpacked into the working tree.
Your job is to land it cleanly into the existing repo conventions.

**Read first, in order:**

1. `CLAUDE.md` — platform invariants. **Do not violate them.**
2. `docs/architecture/bridge-v11.md` — full ecosystem state. Note: ADR-0009
   gate is OPEN; `migrate-to-basic-infra → main` is blocked; do not touch
   `llm/` or `telcoss/compliance/`.
3. `docs/adr/0010-storage-abstraction.md` — the decision you are landing.
4. `docs/runbooks/pdf-intake-storage-migration.md` — migration plan.
   **Not executed in this session.** Phase 1 (pdf-intake adoption) is a
   separate session in a separate repo.

**Hard rules for this session:**

- Do not commit anything. Do not push. Leave working copy ready for my review.
- Do not modify `llm/` (frozen platform contract).
- Do not modify `telcoss/*` (different repo, different session anyway).
- Do not start phases 2-7 of the migration runbook.
- If something looks ambiguous (e.g. existing `CLAUDE.md`, existing
  `docker-compose.yml` topology, existing test conventions) — **stop and
  ask me**, do not guess.

---

## Phases

Execute strictly in order. Phases marked `/goal-friendly` can be batched
under one `/goal` invocation. Phases marked `manual` require pausing for my
review or explicit go-ahead.

### Phase 0 — Reconcile CLAUDE.md (manual)

If `CLAUDE.md.before-week6` exists in the repo root (left by my apply step):

- Diff it against the new `CLAUDE.md`.
- If the old file has content not covered by the new one — propose a
  merged version, show me the diff, **wait for my approval**.
- If the old file is fully covered by the new one — delete the backup.

If no `CLAUDE.md.before-week6` exists, skip this phase.

### Phase 1 — Inventory (manual)

Print:

- `git status --short` for the whole repo.
- `find storage sdk -type f | sort` — what was unpacked.
- Current `pyproject.toml` (or equivalent dep manifest) location and
  format (poetry / hatch / setuptools / uv / ...).
- Current `docker-compose.yml` top-level structure: services list, any
  `include:` directives, any compose-profile pattern in `llm/compose/*.yml`.
- Current test runner: pytest config location, any markers convention
  (`@pytest.mark.integration` etc.).
- Current linter/formatter config: ruff, mypy, black, isort.

Stop. Show me the inventory. **Wait for my "go" before phase 2.**

### Phase 2 — Dependency wiring (/goal-friendly)

Add the storage dependencies to basic-infra's main dep manifest:

- `aiobotocore>=2.12`
- `aiofiles>=23.2`
- `pydantic-settings>=2.2` (probably already present — verify)
- `pydantic>=2.6` (probably already present — verify)

Match the existing dep declaration style (poetry / hatch / etc.). Pin
according to existing pinning convention.

For the SDK (`sdk/basic_infra_storage_client/pyproject.toml`) — adjust
the `packages` config in `[tool.hatch.build.targets.wheel]` if your
build backend differs from hatch. The current entry uses `../../storage`
which works only for hatch + editable install. If you use poetry, switch
to whatever produces the equivalent layout.

### Phase 3 — Lint / typecheck (/goal-friendly)

Run the project's configured linter and typecheck on the new files:

- `ruff check storage/ sdk/`
- `mypy storage/ sdk/` (if mypy is configured)

Fix violations. If a fix would change semantics (not just style) — flag
it and ask before applying.

### Phase 4 — Tests green (/goal-friendly)

Run:

```bash
pytest storage/tests/ sdk/basic_infra_storage_client/tests/ -v
```

Expected: 14 + 3 = 17 passed. If anything is red — diagnose, do not paper over.

### Phase 5 — Compose integration (manual)

Wire `storage/compose/minio.yml` into the project's compose topology.

- If basic-infra uses an `include:` directive at top level — add storage
  compose to the include list.
- If basic-infra uses per-component compose files invoked via `-f` flags
  (like `llm/compose/*.yml` apparently does) — propose the analogous
  pattern for storage. **Show me the proposed change before applying.**
- Add an `.env.example` entry block:

  ```
  # Storage layer (Week 6)
  BASIC_INFRA_STORAGE_BACKEND=minio
  BASIC_INFRA_STORAGE_BUCKET=basic-infra-dev
  BASIC_INFRA_STORAGE_ENDPOINT_URL=http://minio:9000
  BASIC_INFRA_STORAGE_ACCESS_KEY=minioadmin
  BASIC_INFRA_STORAGE_SECRET_KEY=minioadmin
  ```

  Match the existing `.env.example` style.

Do not start MinIO yet. Just wire the config.

### Phase 6 — Live MinIO smoke (manual, optional)

Only if I explicitly say "do the smoke".

```bash
docker compose --profile storage up -d
docker compose logs minio-init   # bucket should be created
```

Then run a one-shot script that does: put → head → get → list →
presigned_url GET → download via httpx → delete. All steps should pass.
Tear down with `docker compose --profile storage down`.

### Phase 7 — Review prep (manual)

- Print `git diff --stat` — summary of changes.
- Print full diff for `docker-compose.yml`, `.env.example`, and any other
  cross-cutting files you touched.
- Print TODO list: anything you decided to defer, anything that needs my
  attention, any rough edges in the code.
- **Do not commit. Stop.**

---

## Reference

- ADR-0010 — `docs/adr/0010-storage-abstraction.md`
- Migration runbook — `docs/runbooks/pdf-intake-storage-migration.md`
- Ecosystem bridge — `docs/architecture/bridge-v11.md`
- Slash commands — `.claude/commands/verify-storage.md`,
  `.claude/commands/storage-status.md`
- Tasklist (this session) — `tasklist.md`
