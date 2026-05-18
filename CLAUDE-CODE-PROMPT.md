# Claude Code Prompt — Week 4 — basic-infra LLM platform

Hi Claude Code. You're starting a **new repository** this time: `basic-infra` — a shared infrastructure platform extracted from two existing projects (`telcoss` and `pamyat-naroda-graph`). Week 4 scope: the **LLM layer** only (generation, embeddings, reranking, multi-tenancy). Storage and observability layers are deferred to Weeks 5–7.

This is NOT a continuation of telcoss Week 3. Telcoss is "done" (PR #3 self-review). The work here is in `~/basic-infra/` (new), with `~/telcoss/` and `~/PAMYAT-NARODA-GRAPH/` as **clients** of this platform after migration.

## Read first (in this exact order)

1. `docs/adr/0001-platform-charter.md` — scope, what we are and aren't
2. `docs/adr/0002-api-contract.md` — OpenAI-compatible + Cohere-style rerank + extensions
3. `docs/adr/0003-multi-tenancy.md` — tenants, auth, rate limits
4. `docs/adr/0004-provider-switching.md` — client-side provider abstraction
5. `docs/adr/0005-backend-pluggability.md` — platform-side backend dispatch
6. `docs/specs/llm-platform-spec.md` — the complete implementation contract
7. `docs/specs/week-4-tasklist.md` — your phased work plan

## What Week 4 produces

A new `basic-infra` repo with:

| Layer                  | Path                                  | Purpose                                          |
| ---------------------- | ------------------------------------- | ------------------------------------------------ |
| Gateway                | `llm/gateway/`                        | FastAPI, OpenAI-compatible, multi-tenant         |
| Backend adapters       | `llm/gateway/app/backends/`           | llama.cpp, TEI embed, TEI rerank, anthropic stub |
| Backend registry       | `llm/backends.yaml`                   | model→backend routing config                     |
| Tenant store           | `llm/gateway/app/tenancy/`            | SQLite + Redis rate limit                        |
| Compose stack          | `llm/compose/`, root `docker-compose` | gateway + Redis + llama-cpp + TEI                |
| Python client SDK      | `client-sdks/python/vams_llm_client/` | provider-agnostic client                         |
| Scripts                | `scripts/`                            | model migration, tenant seed                     |
| Documentation          | `docs/`                               | ADRs, OpenAPI spec, runbooks                     |

By end of Week 4, both `telcoss` and `pamyat-naroda-graph` consume the platform as clients. Telcoss's PR #3 LLM-task is closed via real extraction.

## Operating principles (carry-over from prior weeks)

- **Clean layering** — `gateway/app/api` (HTTP) → `routing` (dispatch) → `backends` (adapters) → external HTTP. No layer skipping.
- **Pydantic v2 schemas** as the single source of truth for request/response shapes. Match `docs/api/openapi.yaml` exactly.
- **Structured logging** with structlog throughout. Every request line includes `tenant_id`, `request_id`, `model`, `backend`, `duration_ms`, `status`.
- **Tests at three levels**: unit (schemas, store logic, adapter translation), integration (testcontainers — real Redis, real SQLite, fake backend FastAPI), e2e (against live backends; marked `@pytest.mark.live`).
- **ruff + mypy-strict** must pass. `pyproject.toml` in each Python package configures both.
- **Docstrings on public functions** explain the contract, not the implementation.

## What you should NOT do

- **Do not invent endpoints** outside `docs/api/openapi.yaml`. If the spec is wrong, fix the spec FIRST, then write code.
- **Do not put domain logic into the platform.** No telecom-specific behavior, no genealogy-specific behavior. If you're tempted, it belongs in a client project, not here.
- **Do not bypass adapter ABCs.** Every backend implements `BackendAdapter`. No direct HTTP from API layer to backend.
- **Do not store prompts.** Prompts are client business logic. The platform is content-agnostic.
- **Do not build streaming, tools/function-calling, or multimodal in v1.** Out of scope per ADR-0002.
- **Do not bind to 0.0.0.0 on the host.** Inside containers fine; on the host, `127.0.0.1:8003:8003` only. Auth is Bearer-token in plain HTTP — only safe on localhost.
- **Do not delete or modify `~/PAMYAT-NARODA-GRAPH/` until Phase 6.** Phase 2 only sets up symlinks; pamyat must keep working through Phases 1–5.

## Tasklist execution order

Strictly follow `docs/specs/week-4-tasklist.md`. Phases:

1. **Bootstrap** (manual review)
2. **Model migration** (manual — file system surgery)
3. **Gateway core** (`/goal-friendly` — template-heavy code)
4. **Backend adapters & router** (`/goal-friendly`)
5. **Live compose stack** (manual — first real bring-up)
6. **Client SDK + pamyat-naroda migration** (manual — irreversible)
7. **Telcoss migration + close PR #3 LLM-task** (manual)
8. **Cleanup, docs, bridge v8** (`/goal-friendly`)

For phases marked `/goal-friendly`, you may use `/goal` + auto mode. The success criteria for each are listed at the end of the phase section in the tasklist. For manual phases, commit after each significant step and pause for review.

## Quality bar

- Type hints on every public function. No `Any` without `# type: ignore[<reason>]` explaining why.
- Tests for every adapter, every use case, every API route. Minimum: happy path + one failure path.
- Migrations of model files (Phase 2) are reversible via symlinks — pamyat-naroda must keep working at every commit.
- OpenAPI spec validates with `openapi-spec-validator`. CI hook checks this.
- Logs are structured JSON in production; pretty console in dev.

## When you hit ambiguity

1. Re-read the relevant ADR.
2. Check `docs/specs/llm-platform-spec.md` for the precise contract.
3. If still unclear — pick the more conservative option and leave a `# TODO(week4-review):` comment.
4. Never invent behavior. If business logic is unclear, stop and flag it in the commit message.

## Output per phase

Each phase ends with:

1. Code that meets the phase's success criteria
2. Tests at the appropriate levels
3. Commit with `[week4-phase-N]` prefix
4. If it's a `/goal-friendly` phase — final summary printed; if it's manual — stop and wait for human "Продолжай".

## End-of-Week-4 verification

These must all return zero exit code before Week 4 is closed:

```bash
# basic-infra side
cd ~/basic-infra
make test-all                       # gateway + SDK unit + integration tests pass
make lint                           # ruff + mypy-strict clean
make up DEFAULT_PROFILE=llm-cpu     # stack comes up on CPU (works without GPU)
make status                         # /ready returns 200, all backends healthy
make tenants-seed                   # creates telcoss and pamyat-naroda; capture keys

# Smoke tests with curl (using captured key)
curl -H "Authorization: Bearer $TELCOSS_KEY" http://localhost:8003/v1/models | jq
curl -H "Authorization: Bearer $TELCOSS_KEY" -X POST \
  http://localhost:8003/v1/embeddings \
  -d '{"model":"bge-m3","input":["test"]}' | jq '.data | length'   # → 1

# pamyat-naroda side — must work as a client
cd ~/PAMYAT-NARODA-GRAPH
docker compose up -d                # no LLM services in compose anymore
# (run pamyat's smoke tests — they should all pass against basic-infra)

# telcoss side — close the LLM-task from PR #3
cd ~/telcoss
poetry run telcoss pdf-intake submit --file tests/fixtures/yurlovo-nss-rd.pdf
# ... full pipeline through extract; assert ≥1 Manhole fact created
```

If all green — Week 4 is closed.

---

Begin with Phase 1. Read the documents in the order above before writing any code. `bridge-v7.md` is attached as context for what state `telcoss` is in (Week 3 done, PR #3 in self-review) — that work is not part of Week 4 but it's a client downstream.
