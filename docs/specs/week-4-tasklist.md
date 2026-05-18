# Week 4 — Tasklist for Claude Code

Execution plan for `basic-infra` platform. 8 phases, ~9 working days expected. Each phase ends with a commit `[week4-phase-N]` and a stop for review — EXCEPT phases explicitly marked **`/goal-friendly`** where Claude Code can use `/goal` + auto mode to run unattended.

---

## Phase 1 — Bootstrap repo + ADRs + API spec  *(manual; foundation)*

Reference: ADR-0001 through 0005.

### 1.1 Repo skeleton

Create directory structure per `docs/specs/llm-platform-spec.md` § "Module layout".

### 1.2 Documentation

- Copy 5 ADRs into `docs/adr/`.
- Write `README.md` at repo root with: purpose, quick start, links to ADRs.
- Write `docs/api/openapi.yaml` — formal OpenAPI 3.1 spec for all `/v1/*` endpoints. This is the single source of truth for the contract.
- Write runbook stubs: `docs/runbooks/adding-a-backend.md`, `managing-tenants.md`, `model-migration.md`.

### 1.3 Tooling

- `pyproject.toml` for gateway (Python 3.12, FastAPI, Pydantic v2, structlog, httpx, redis, pydantic-settings)
- `pyproject.toml` for client SDK
- Top-level `Makefile`
- `.env.example`
- `.gitignore` (tenants.db, models/, hf-cache, *.pyc)
- `docker-compose.yml` (skeleton — services empty, profiles defined)

### 1.4 Commit

```
[week4-phase-1] Bootstrap basic-infra repo: ADRs, OpenAPI spec, tooling
```

**Stop. Human review the OpenAPI spec carefully — this is the contract.**

---

## Phase 2 — Model migration from pamyat-naroda  *(manual; one-time)*

This phase is **infrastructure / file system work**, not coding. Best executed by Claude Code via shell, with human review of each step.

### 2.1 Create new model location

```bash
mkdir -p ~/llm-models
```

### 2.2 Move T-pro GGUF

```bash
mv ~/PAMYAT-NARODA-GRAPH/models/T-pro-it-2.1-Q8_0.gguf ~/llm-models/
# Symlink in old location so pamyat-naroda still works pre-migration
ln -s ~/llm-models/T-pro-it-2.1-Q8_0.gguf ~/PAMYAT-NARODA-GRAPH/models/T-pro-it-2.1-Q8_0.gguf
```

### 2.3 Move bge-m3 if present locally

If `~/PAMYAT-NARODA-GRAPH/models/bge-m3/` exists — `mv` to `~/llm-models/bge-m3/` + symlink.

### 2.4 Migrate HF cache

```bash
mkdir -p ~/llm-models/hf-cache
# pn_reranker's cache lives in ~/PAMYAT-NARODA-GRAPH/models/hf-cache (post-PR3-fix)
mv ~/PAMYAT-NARODA-GRAPH/models/hf-cache/* ~/llm-models/hf-cache/ || true
```

### 2.5 Verify pamyat-naroda still works

```bash
cd ~/PAMYAT-NARODA-GRAPH
docker compose restart reranker llm-gateway retrieval
docker compose logs --tail 20 reranker llm-gateway retrieval
# all should report startup complete
```

### 2.6 Commit (in basic-infra repo)

```
[week4-phase-2] Document model migration path

scripts/migrate-models-from-pamyat.sh provided. Models now live at
~/llm-models/ and are bind-mounted into both ecosystems. Pamyat-naroda
unchanged; will switch to platform consumption in Phase 6.
```

**Stop. Confirm `pamyat-naroda-graph` containers are healthy after symlink swap.**

---

## Phase 3 — Gateway core: API + auth + tenancy  *(`/goal-friendly`)*

This is template-heavy work: implement FastAPI app with routes, request models, tenant resolution. Well-defined success: pytest passes for unit + integration.

### 3.1 FastAPI app structure

- `llm/gateway/app/main.py` — FastAPI instance, lifespan, route mount, structured logging
- `llm/gateway/app/config.py` — Pydantic Settings (GATEWAY_*, REDIS_URL, etc.)
- `llm/gateway/app/api/v1/{chat,completions,embeddings,rerank,models,tenants}.py` — route stubs
- `llm/gateway/app/api/deps.py` — `current_tenant` dependency, extracts from Bearer token

### 3.2 Pydantic schemas

`llm/gateway/app/schemas/*.py` — request/response models matching OpenAPI spec:
- `chat.py` — `ChatCompletionRequest`, `ChatCompletionResponse`, `ChatMessage`, `ResponseFormat`, `JsonSchemaResponseFormat`
- `completions.py` — text-completion equivalents
- `embeddings.py` — `EmbeddingRequest`, `EmbeddingResponse`, `EmbeddingData`
- `rerank.py` — `RerankRequest`, `RerankResponse`, `RerankResult`
- `models.py` — `Model`, `ModelList`
- `errors.py` — OpenAI-style error envelope
- `tenant.py` — internal tenant DTOs

### 3.3 Tenancy

- `llm/gateway/app/tenancy/store.py` — SQLite-backed CRUD (sqlalchemy or raw sqlite3, simple)
- `llm/gateway/app/tenancy/auth.py` — Bearer token → tenant lookup with in-memory LRU cache
- `llm/gateway/app/tenancy/ratelimit.py` — Redis token-bucket; `RATE_LIMIT_FAIL_OPEN` env var controls behavior on Redis outage
- `llm/gateway/app/tenancy/cli.py` — typer/argparse CLI for tenant create/list/rotate/delete/smoke-test

### 3.4 Tests

- Unit tests for tenancy store, schema validation, auth dependency
- Integration tests using testcontainers (real Redis, real SQLite file): create tenant, hit `/v1/models` with key, get 200; rotate key, old key works for 24h then 401
- All routes return correct status codes for: missing auth, invalid auth, valid auth + non-existent model

### 3.5 Commit

```
[week4-phase-3] Gateway core: FastAPI app, schemas, tenancy, rate limit
```

**`/goal` is appropriate** here — success criteria: all tests green, `make test` returns zero, OpenAPI spec validates against schemas.

---

## Phase 4 — Backend adapters & router  *(`/goal-friendly`)*

Adapters that translate platform API → backend API per ADR-0005. Each adapter implements `BackendAdapter` ABC.

### 4.1 Adapter ABC

`llm/gateway/app/backends/base.py`:

```python
class BackendAdapter(ABC):
    name: str
    base_url: str
    
    @abstractmethod
    async def chat_completion(self, request: ChatCompletionRequest, model: BackendModel) -> ChatCompletionResponse: ...
    @abstractmethod
    async def embedding(self, request: EmbeddingRequest, model: BackendModel) -> EmbeddingResponse: ...
    @abstractmethod
    async def rerank(self, request: RerankRequest, model: BackendModel) -> RerankResponse: ...
    @abstractmethod
    async def health(self) -> bool: ...
    def supports(self, capability: str) -> bool: ...
```

### 4.2 Concrete adapters

- `openai_compat.py` — pure proxy for llama.cpp-server (which speaks OpenAI). Translates `response_format` → llama grammar where supported.
- `tei.py` — embeddings, translates OpenAI shape to TEI's `/embed` endpoint
- `tei_rerank.py` — rerank against TEI's `/rerank`
- `vllm.py` — extends openai_compat with `guided_json` parameter forwarding (deferred — stub for now if no vLLM available)
- `anthropic.py` — stub (deferred to Week 5 unless time)

### 4.3 Backend registry

`llm/gateway/app/routing/registry.py` — loads `backends.yaml`, validates schema (Pydantic), exposes `Registry.get_backend_for(model_id: str) -> BackendAdapter`.

`llm/gateway/app/routing/router.py` — central dispatcher. Wires request from API layer through router → adapter.

`llm/gateway/app/routing/health.py` — background task, calls `adapter.health()` every `BACKEND_HEALTH_INTERVAL_SECONDS`, marks unhealthy adapters in registry. `/ready` checks all adapters.

### 4.4 Tests

- Unit: each adapter's translation logic with mocked HTTP
- Integration: spin up a fake openai-compat server (FastAPI inside the test) and verify end-to-end through router
- Integration: backends.yaml with a missing model → router raises `ModelNotFound`
- Integration: backends.yaml referencing unreachable backend → health task marks unhealthy after 3 fails, `/ready` returns 503

### 4.5 Commit

```
[week4-phase-4] Backend adapters: openai-compat, tei, tei-rerank + router
```

**`/goal` appropriate.** Success: tests green, `/v1/models` shows registered models, dispatch round-trip works against fake backend.

---

## Phase 5 — Compose & live integration  *(manual; deployment)*

Wire everything into docker-compose and bring up the live stack against real T-pro/BGE.

### 5.1 Compose files

- `docker-compose.yml` (root) wires profiles per `llm-platform-spec.md`
- `llm/compose/compose.gateway.yml` — the FastAPI service
- `llm/compose/compose.llama-cpp.yml` — T-pro CPU/GPU profiles (copy from pamyat-naroda)
- `llm/compose/compose.tei.yml` — embed + rerank
- `llm/compose/compose.redis.yml` — for rate limit

### 5.2 backends.yaml

Real config:

```yaml
backends:
  - name: llama-cpp-tpro
    kind: openai_compat
    base_url: http://tpro-backend:8080/v1
    models:
      - id: t-pro-it-2.1-q8
        backend_model_name: T-pro-it-2.1-Q8_0.gguf
        capabilities: [chat, completions, structured]
  - name: tei-embed
    kind: tei
    base_url: http://tei-embed:80
    models:
      - id: bge-m3
        backend_model_name: BAAI/bge-m3
        capabilities: [embeddings]
  - name: tei-rerank
    kind: tei_rerank
    base_url: http://tei-rerank:80
    models:
      - id: bge-reranker-v2-m3
        backend_model_name: BAAI/bge-reranker-v2-m3
        capabilities: [rerank]
```

### 5.3 Bring up

```bash
make up        # profile: basic + llm-gpu (or llm-cpu)
make status    # all backends healthy
```

### 5.4 Seed tenants

```bash
scripts/seed-tenants.py
# Creates 'telcoss' and 'pamyat-naroda' with allowed_models='*'.
# Prints generated API keys — save them.
```

### 5.5 Smoke tests

```bash
# Models listing
curl -H "Authorization: Bearer $TELCOSS_KEY" http://localhost:8003/v1/models | jq

# Chat
curl -H "Authorization: Bearer $TELCOSS_KEY" -X POST http://localhost:8003/v1/chat/completions \
  -d '{"model": "t-pro-it-2.1-q8", "messages": [{"role": "user", "content": "Привет"}]}' | jq

# Embedding
curl -H "Authorization: Bearer $TELCOSS_KEY" -X POST http://localhost:8003/v1/embeddings \
  -d '{"model": "bge-m3", "input": ["hello", "world"]}' | jq '.data | length'

# Rerank
curl -H "Authorization: Bearer $TELCOSS_KEY" -X POST http://localhost:8003/v1/rerank \
  -d '{"model": "bge-reranker-v2-m3", "query": "телекоммуникации", "documents": ["сеть связи", "молоко"], "top_n": 2}' | jq
```

### 5.6 Commit

```
[week4-phase-5] Live compose stack: gateway + llama-cpp T-pro + TEI embed/rerank
```

**Stop. Verify all smoke tests return 200 with sensible content.**

---

## Phase 6 — Client SDK + pamyat-naroda migration  *(manual; integration)*

### 6.1 Build SDK

`client-sdks/python/vams_llm_client/`:
- `client.py` — `LlmClient.from_env()`, dispatches to providers
- `providers/basic_infra.py` — uses `httpx.AsyncClient`, full feature support
- `providers/openai.py` — uses `openai` Python package, gracefully handles missing rerank
- `providers/anthropic.py` — uses `anthropic` Python package, gracefully handles missing embed/rerank, translates `response_format` to tool_use
- `capabilities.py`
- `cache.py` — SQLite embedding cache (opt-in)
- `errors.py`

Unit tests for each provider with mocked HTTP. Integration tests against the live platform from Phase 5.

### 6.2 Publish SDK locally

```bash
cd client-sdks/python
poetry build
# wheel produced; for now consumed via Poetry path dependency
```

### 6.3 Migrate pamyat-naroda

In `~/PAMYAT-NARODA-GRAPH`:

```bash
# Branch
git checkout -b migrate-to-basic-infra

# pyproject.toml — add path dep
poetry add ../basic-infra/client-sdks/python

# Remove LLM services from docker-compose.yml
# Delete: llm-gateway, reranker, retrieval (well — see below), tpro-backend-cpu, tpro-backend-gpu

# In services/<wherever>: replace HTTP calls with SDK calls
# (Claude Code does the bulk; human reviews diff)

# .env.local
echo "LLM_PROVIDER=basic-infra" >> .env
echo "LLM_BASE_URL=http://host.docker.internal:8003/v1" >> .env
echo "LLM_API_KEY=$(cat ~/secrets/basic-infra/pamyat-naroda.key)" >> .env

# Test
docker compose up -d
make test  # smoke tests of pn workflows
```

### 6.4 Retrieval split

`pn_retrieval` did vector search + embedding. Now:
- Embedding → SDK call
- Vector search → stays inside pamyat as project code (it owns faiss)

This may involve splitting `pn_retrieval` into a thinner service or absorbing its remaining vector-search logic into another pamyat service. Claude Code reads pn's code, makes the right call.

### 6.5 `/analyze` endpoint

This was pamyat-specific. Either:
- Move into a pamyat-internal route/module (recommended)
- Or keep as a small pamyat-side wrapper that uses SDK underneath

Either way — `/analyze` does NOT exist in basic-infra. Document the change in pamyat's CHANGELOG.

### 6.6 Commit (in pamyat-naroda repo)

```
feat(infra): consume basic-infra LLM platform

- Removed llm-gateway, reranker, tpro-backend services from compose
- Added vams-llm-client as path dependency
- Refactored HTTP calls to use SDK
- /analyze logic moved to <pamyat module>
- pn_retrieval split: embedding via SDK, vector search remains internal
```

### 6.7 Commit (in basic-infra repo)

```
[week4-phase-6] vams-llm-client SDK + pamyat-naroda migration
```

**Stop. Run pamyat-naroda's full test suite, smoke-test its production workflow against basic-infra. Pamyat must work end-to-end before continuing.**

---

## Phase 7 — Telcoss migration + close PR #3 LLM-task  *(manual; integration)*

### 7.1 Migrate telcoss adapters

In `~/telcoss`:

```bash
git checkout -b migrate-to-basic-infra

poetry add ../basic-infra/client-sdks/python

# Replace in src/telcoss/pdf_intake/infrastructure/adapters/
#   vllm_generation.py    → calls client.chat.completions
#   tei_embedding.py      → calls client.embeddings
#   tei_reranking.py      → calls client.rerank

# .env
echo "LLM_PROVIDER=basic-infra" >> .env
echo "LLM_BASE_URL=http://localhost:8003/v1" >> .env
echo "LLM_API_KEY=$(cat ~/secrets/basic-infra/telcoss.key)" >> .env
```

### 7.2 Tests

- All existing unit/integration tests for adapters stay green (they mock the SDK now instead of httpx)
- New e2e test: `tests/e2e/llm/test_real_extraction.py` (marked `@pytest.mark.live`) — runs `telcoss pdf-intake extract` on `tests/fixtures/yurlovo-nss-rd.pdf`, asserts ≥1 Manhole extracted with non-empty name

### 7.3 Run the LLM extraction end-to-end

```bash
cd ~/telcoss
make dev   # ensures Postgres etc up
# basic-infra already up from Phase 5
poetry run telcoss pdf-intake submit --file tests/fixtures/yurlovo-nss-rd.pdf
poetry run telcoss pdf-intake parse --document-id <uuid>
poetry run telcoss pdf-intake embed --document-id <uuid>
poetry run telcoss pdf-intake extract --document-id <uuid> --target Manhole
poetry run telcoss pdf-intake list-facts --document-id <uuid>
```

Expected: list-facts returns ≥1 fact of type Manhole with `lifecycle=draft`.

### 7.4 Commit (in telcoss repo)

```
feat(pdf-intake): consume basic-infra LLM platform

Closes the open LLM-task from PR #3 — real end-to-end extraction now
exercised against the basic-infra platform (T-pro Q8 + BGE-M3 + BGE-Reranker-v2-m3).
```

If telcoss PR #3 hasn't merged yet — this becomes a follow-up commit on the same branch and the open test-plan item gets checked.

### 7.5 Commit (in basic-infra repo)

```
[week4-phase-7] Telcoss migration; PR #3 LLM-task closed via real extraction
```

**Stop. Both ecosystems now consume the platform.**

---

## Phase 8 — Cleanup, docs, bridge update  *(`/goal-friendly`)*

### 8.1 Docs

- Fill in `docs/runbooks/adding-a-backend.md`, `managing-tenants.md`, `model-migration.md`
- Fill in `docs/client-integration/telcoss.md` and `pamyat-naroda.md` with the actual integration patterns used
- Polish `README.md`: quick start, troubleshooting, "what's next"

### 8.2 Repo health

- `pre-commit` hooks: black, ruff, mypy-strict
- CI workflow stub (`.github/workflows/test.yml`) — runs pytest + ruff + mypy
- Coverage report ≥80% for gateway, ≥70% for SDK

### 8.3 Bridge v8 (for the next session)

Update `bridge-v7.md` for telcoss → `bridge-v8.md`:
- Telcoss state: Week 3 done + migrated to basic-infra
- Pamyat state: migrated to basic-infra
- Roadmap update: Week 5 = Compliance BC (telcoss); Week 6 = storage layer of basic-infra; Week 7+ as before

### 8.4 Commit

```
[week4-phase-8] Cleanup, docs, CI scaffolding, bridge v8
```

**Done. Open PR in basic-infra repo, optionally tag v0.1.0.**

---

## Where `/goal` + auto mode is appropriate vs not

| Phase | Mode             | Reason                                                      |
| ----- | ---------------- | ----------------------------------------------------------- |
| 1     | manual           | Architectural baseline; review of API spec mandatory        |
| 2     | manual           | File system surgery; symlinks can wreck pamyat if wrong     |
| **3** | **`/goal`**      | Template-heavy code; clear success criteria (tests green)   |
| **4** | **`/goal`**      | Same — adapter pattern is well-defined                      |
| 5     | manual           | First live bring-up; you want to see logs in real time      |
| 6     | manual           | Migration of pamyat — irreversible; review needed           |
| 7     | manual           | Closes the LLM-task; correctness matters                    |
| **8** | **`/goal`**      | Polish, docs, CI scaffolding — low-risk                     |

For `/goal` phases:

```
/goal Implement Phase 3 of docs/specs/week-4-tasklist.md.

Success criteria:
- All unit and integration tests in llm/gateway/tests/ pass
- `make lint` returns zero (ruff + mypy-strict)
- OpenAPI spec at docs/api/openapi.yaml validates against route signatures
- Manual smoke: `basic-infra tenant create --id test --models "*"` and
  curl /v1/models with the returned key returns 200 with empty data
  (no models registered yet — Phase 4)

When done, commit with [week4-phase-3] prefix and stop.
```

---

## Estimated effort

| Phase | Days  |
|-------|-------|
| 1 — Bootstrap                       | 1     |
| 2 — Model migration                 | 0.5   |
| 3 — Gateway core (`/goal`)          | 1.5   |
| 4 — Backends (`/goal`)              | 1.5   |
| 5 — Compose live                    | 0.5   |
| 6 — SDK + pamyat                    | 1.5   |
| 7 — Telcoss migration               | 1     |
| 8 — Cleanup (`/goal`)               | 1     |
| **Total**                           | **~9** |

If `/goal` phases run faster than expected (no review pauses) — likely 6-7 days end to end.

---

## What this tasklist intentionally does NOT cover

- Storage primitives (Week 6)
- Observability beyond `/health` (Week 6)
- Compliance BC in telcoss (Week 5)
- LLM streaming or tools (defer until concrete need)
- High-availability deployment
- Public exposure (TLS, OAuth, WAF)
