# Tasklist — Week 6 (basic-infra storage layer)

Sequential phases. `/goal-friendly` phases can be batched under one `/goal`
invocation; `manual` phases require my review/approval before proceeding.

---

## Phase 0 — Reconcile CLAUDE.md (manual)

- [ ] Check if `CLAUDE.md.before-week6` exists
- [ ] If yes — diff against new `CLAUDE.md`, propose merge, wait for approval
- [ ] If no — skip

## Phase 1 — Inventory (manual)

- [ ] `git status --short`
- [ ] `find storage sdk -type f | sort` — verify what was unpacked
- [ ] Locate and characterize `pyproject.toml` / dep manifest
- [ ] Locate and characterize top-level `docker-compose.yml`
- [ ] Locate compose-profile pattern in `llm/compose/*.yml` (precedent)
- [ ] Identify test runner config, marker conventions
- [ ] Identify linter/formatter config (ruff/mypy/black/isort)
- [ ] **Pause for "go".**

## Phase 2 — Dependency wiring (/goal-friendly)

- [ ] Add `aiobotocore>=2.12` to basic-infra manifest
- [ ] Add `aiofiles>=23.2` to basic-infra manifest
- [ ] Verify `pydantic-settings>=2.2` present (add if missing)
- [ ] Verify `pydantic>=2.6` present (add if missing)
- [ ] Adjust `sdk/basic_infra_storage_client/pyproject.toml` `packages`
      config if build backend differs from hatch

## Phase 3 — Lint / typecheck (/goal-friendly)

- [ ] `ruff check storage/ sdk/`
- [ ] `mypy storage/ sdk/` (if configured)
- [ ] Apply style fixes
- [ ] Flag semantic-changing fixes for review

## Phase 4 — Tests green (/goal-friendly)

- [ ] `pytest storage/tests/ -v` — 14/14 passed
- [ ] `pytest sdk/basic_infra_storage_client/tests/ -v` — 3/3 passed
- [ ] Diagnose any failures, do not paper over

## Phase 5 — Compose integration (manual)

- [ ] Determine compose topology pattern (include / -f flags / profiles)
- [ ] Propose wiring for `storage/compose/minio.yml`
- [ ] **Show me proposed change. Wait for approval.**
- [ ] Apply approved wiring
- [ ] Add storage env block to `.env.example`

## Phase 6 — Live MinIO smoke (manual, optional)

- [ ] **Only if I say "do the smoke".**
- [ ] `docker compose --profile storage up -d`
- [ ] Verify `minio-init` created bucket
- [ ] Smoke: put → head → get → list → presigned GET → httpx download → delete
- [ ] `docker compose --profile storage down`

## Phase 7 — Review prep (manual)

- [ ] `git diff --stat`
- [ ] Full diff for `docker-compose.yml`, `.env.example`, cross-cutting files
- [ ] TODO list of deferred items / open questions / rough edges
- [ ] **Do NOT commit. Stop. Hand off for review.**

---

## Don't list

- [ ] **Don't** touch `llm/` (frozen platform contract)
- [ ] **Don't** touch `telcoss/*` (different repo)
- [ ] **Don't** start migration runbook phases 2-7
- [ ] **Don't** commit or push
- [ ] **Don't** merge `week6-storage-layer` anywhere
- [ ] **Don't** close ADR-0009 gate
