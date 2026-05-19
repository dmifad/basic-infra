# basic-infra

Shared infrastructure platform for personal projects (`telcoss`, `pamyat-naroda-graph`, future).

Week 4 scope: **LLM layer**. Storage and observability layers come later (Weeks 5–7).

## What you get

```
                                    ┌─────────────────────┐
                                    │ basic-infra LLM     │
                                    │ ─────────────────── │
            Authorization: Bearer   │ POST /v1/chat/...   │
            X-Tenant-ID (optional)  │ POST /v1/embeddings │
            ──────────────────────► │ POST /v1/rerank     │
                                    │ GET  /v1/models     │
                                    └──────────┬──────────┘
                                               │ routes by model
              ┌────────────────────────────────┼────────────────────┐
              ▼                                ▼                    ▼
     ┌─────────────────┐            ┌─────────────────┐    ┌─────────────────┐
     │ llama.cpp       │            │ TEI embeddings  │    │ TEI rerank      │
     │ T-pro Q8/FP8    │            │ BGE-M3          │    │ BGE-Reranker-v2 │
     └─────────────────┘            └─────────────────┘    └─────────────────┘
```

OpenAI-compatible HTTP API (`/v1/chat/completions`, `/v1/embeddings`, `/v1/models`) plus a Cohere-style `/v1/rerank`. Every consumer is a tenant with its own API key and rate limits.

## Quick start

```bash
# 1. Migrate existing models (from pamyat-naroda, if applicable)
make models-migrate

# 2. Configure
cp .env.example .env.local
$EDITOR .env.local

# 3. Bring up the stack (default: GPU profile)
make up                            # GPU
# or
make up DEFAULT_PROFILE=llm-cpu    # CPU fallback

# 4. Seed default tenants
make tenants-seed
# → prints API keys for "telcoss" and "pamyat-naroda" — save these somewhere safe

# 5. Verify
make status                        # /ready returns 200 once backends are up
curl -H "Authorization: Bearer <key>" http://localhost:8003/v1/models | jq
```

## Architecture

Read in this order for a full picture:

1. [`docs/adr/0001-platform-charter.md`](docs/adr/0001-platform-charter.md) — what we are and what we are not
2. [`docs/adr/0002-api-contract.md`](docs/adr/0002-api-contract.md) — OpenAI-compatible + extensions
3. [`docs/adr/0003-multi-tenancy.md`](docs/adr/0003-multi-tenancy.md) — auth, rate limits
4. [`docs/adr/0004-provider-switching.md`](docs/adr/0004-provider-switching.md) — how clients pick local vs cloud LLM
5. [`docs/adr/0005-backend-pluggability.md`](docs/adr/0005-backend-pluggability.md) — how platform picks the backend per model

For client integration:
- [`docs/client-integration/telcoss.md`](docs/client-integration/telcoss.md)
- [`docs/client-integration/pamyat-naroda.md`](docs/client-integration/pamyat-naroda.md)

For ops:
- [`docs/runbooks/adding-a-backend.md`](docs/runbooks/adding-a-backend.md)
- [`docs/runbooks/managing-tenants.md`](docs/runbooks/managing-tenants.md)
- [`docs/runbooks/model-migration.md`](docs/runbooks/model-migration.md)

## Client SDK

Python projects consume the platform via [`client-sdks/python/`](client-sdks/python/) (`vams-llm-client` package):

```python
from vams_llm_client import LlmClient

client = LlmClient.from_env()       # reads LLM_PROVIDER, LLM_BASE_URL, LLM_API_KEY

resp = client.chat.completions.create(
    model="t-pro-it-2.1-q8",
    messages=[{"role": "user", "content": "Привет"}],
)
```

Provider-agnostic: set `LLM_PROVIDER=openai` or `LLM_PROVIDER=anthropic` in your project's env to switch from the local platform to cloud — no code changes.

## Status

| Layer            | Status        | Notes                                          |
| ---------------- | ------------- | ---------------------------------------------- |
| LLM gateway      | ✅ Week 4     | OpenAI + rerank contract, multi-tenant         |
| LLM backends     | ✅ Week 4     | llama.cpp (T-pro), TEI embed/rerank            |
| Client SDK       | ✅ Week 4     | basic-infra + openai + anthropic providers     |
| Storage layer    | Week 6 plan   | Postgres-multi-db, Redis, MinIO as shared svcs |
| Observability    | Week 6 plan   | Prometheus, Loki, Grafana                      |
| MCP server       | Future        | For Claude desktop integration                 |

Both `telcoss` and `pamyat-naroda` consume the platform as clients — see
[`docs/bridge-v8.md`](docs/bridge-v8.md) for the Week 4 end state.

## Repository layout

```
basic-infra/
├── docs/                  → ADRs, OpenAPI spec, runbooks, integration guides
├── llm/                   → gateway service + backend adapters + compose
│   ├── gateway/           → FastAPI app
│   ├── backends.yaml      → registry of backends and models
│   └── compose/           → per-stack compose files
├── client-sdks/python/    → vams-llm-client package
├── scripts/               → seed-tenants, model migration
├── tenants/               → SQLite tenant store (gitignored)
└── models/README.md       → where models live (host bind to ~/llm-models)
```

## License

Personal project — no license declared.
