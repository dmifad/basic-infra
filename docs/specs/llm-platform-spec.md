# LLM Platform — domain & implementation specification

References ADR-0001 through ADR-0005. This is the contract Claude Code implements in Week 4.

## Module layout (within `basic-infra` repo)

```
basic-infra/
├── README.md
├── Makefile                              ← make up | down | logs | status | test
├── .env.example                          ← all env vars documented
├── docker-compose.yml                    ← top-level orchestration
├── docs/
│   ├── adr/
│   │   ├── 0001-platform-charter.md     ← (copied from package)
│   │   ├── 0002-api-contract.md
│   │   ├── 0003-multi-tenancy.md
│   │   ├── 0004-provider-switching.md
│   │   └── 0005-backend-pluggability.md
│   ├── api/
│   │   └── openapi.yaml                  ← formal API spec
│   ├── runbooks/
│   │   ├── adding-a-backend.md
│   │   ├── managing-tenants.md
│   │   └── model-migration.md
│   └── client-integration/
│       ├── telcoss.md
│       └── pamyat-naroda.md
├── llm/
│   ├── gateway/                          ← the FastAPI service
│   │   ├── Dockerfile
│   │   ├── pyproject.toml
│   │   └── app/
│   │       ├── __init__.py
│   │       ├── main.py                   ← FastAPI app, lifespan, route mount
│   │       ├── config.py                 ← Pydantic Settings
│   │       ├── api/
│   │       │   ├── v1/
│   │       │   │   ├── chat.py
│   │       │   │   ├── completions.py
│   │       │   │   ├── embeddings.py
│   │       │   │   ├── rerank.py
│   │       │   │   ├── models.py
│   │       │   │   └── tenants.py
│   │       │   └── deps.py               ← auth dependency, tenancy resolver
│   │       ├── routing/
│   │       │   ├── registry.py           ← loads backends.yaml
│   │       │   ├── router.py             ← model → backend dispatcher
│   │       │   └── health.py             ← background health checks
│   │       ├── backends/
│   │       │   ├── __init__.py
│   │       │   ├── base.py               ← abstract BackendAdapter
│   │       │   ├── openai_compat.py      ← llama.cpp, vllm, openai
│   │       │   ├── tei.py                ← embeddings
│   │       │   ├── tei_rerank.py
│   │       │   ├── anthropic.py
│   │       │   └── translate.py          ← OpenAI↔Anthropic translation
│   │       ├── tenancy/
│   │       │   ├── store.py              ← SQLite-backed tenant CRUD
│   │       │   ├── auth.py               ← bearer-token verification
│   │       │   ├── ratelimit.py          ← Redis token-bucket
│   │       │   └── cli.py                ← `basic-infra tenant ...` commands
│   │       ├── schemas/                  ← Pydantic v2 schemas
│   │       │   ├── chat.py
│   │       │   ├── completions.py
│   │       │   ├── embeddings.py
│   │       │   ├── rerank.py
│   │       │   ├── models.py
│   │       │   ├── errors.py
│   │       │   └── tenant.py
│   │       └── observability/
│   │           ├── logging.py            ← structlog with tenant context
│   │           └── metrics.py            ← Prometheus stubs (real in Week 6)
│   ├── backends.yaml                     ← backend registry
│   ├── compose/
│   │   ├── compose.gateway.yml           ← FastAPI service
│   │   ├── compose.llama-cpp.yml         ← T-pro CPU/GPU profiles
│   │   ├── compose.tei.yml               ← embed + rerank
│   │   ├── compose.redis.yml             ← for rate limit
│   │   └── compose.dev.yml               ← dev-only convenience services
│   └── tests/
│       ├── unit/
│       ├── integration/
│       └── e2e/
├── client-sdks/
│   └── python/
│       ├── pyproject.toml                ← `vams-llm-client` package
│       ├── README.md
│       ├── vams_llm_client/
│       │   ├── __init__.py
│       │   ├── client.py                 ← LlmClient.from_env()
│       │   ├── providers/
│       │   │   ├── basic_infra.py
│       │   │   ├── openai.py
│       │   │   └── anthropic.py
│       │   ├── capabilities.py
│       │   ├── cache.py                  ← embedding cache (opt-in)
│       │   └── errors.py
│       └── tests/
├── tenants/
│   └── tenants.db                        ← SQLite (gitignored; seeded by CLI)
├── models/
│   └── README.md                         ← document where models go (host bind)
└── scripts/
    ├── bootstrap.sh                      ← creates tenants, downloads models
    ├── seed-tenants.py                   ← creates telcoss + pamyat-naroda
    └── healthcheck.sh                    ← smoke-test all endpoints
```

## API surface — formal contract

### POST /v1/chat/completions

OpenAI-compatible. Required fields: `model`, `messages`. Optional: `temperature`, `top_p`, `max_tokens`, `stop`, `response_format`, `seed`, `n` (only `n=1` supported in v1).

Response: OpenAI shape with `choices`, `usage`, `model`, `id`.

Vendor extension on response:

```json
"metadata": {
  "backend": "llama-cpp-tpro",
  "response_format_fallback": false
}
```

### POST /v1/embeddings

Required: `model`, `input` (string or array). Optional: `dimensions` (some models support; for BGE-M3 ignored).

Response: OpenAI shape with `data` (array of `{embedding, index, object}`), `usage`, `model`.

### POST /v1/rerank

Cohere-style (per ADR-0002).

```json
Request:
{
  "model": "bge-reranker-v2-m3",
  "query": "<query>",
  "documents": ["doc1", "doc2", ...],
  "top_n": 5,
  "return_documents": true
}

Response:
{
  "model": "bge-reranker-v2-m3",
  "results": [
    {"index": 2, "relevance_score": 0.94, "document": {"text": "..."}},
    ...
  ]
}
```

### GET /v1/models

Returns models available to the **current tenant** (after `allowed_models` filtering). Standard OpenAI shape: `{"object": "list", "data": [{"id": ..., "object": "model", "owned_by": ..., "capabilities": [...]}, ...]}`.

The `capabilities` array is a vendor extension (`chat`, `completions`, `embeddings`, `rerank`, `structured`). Standard SDKs ignore unknown fields.

### Operational endpoints

```
GET /health       → 200 {"status": "ok"}
GET /ready        → 200 if backends healthy, 503 otherwise. Body shows per-backend status.
GET /v1/tenants/me → identity of authenticated tenant (debugging)
```

## Configuration via env

```bash
# Platform itself
GATEWAY_HOST=0.0.0.0
GATEWAY_PORT=8003
GATEWAY_LOG_LEVEL=INFO

# Tenant store
TENANT_DB_PATH=/data/tenants/tenants.db

# Rate limit
REDIS_URL=redis://redis:6379/0
RATE_LIMIT_FAIL_OPEN=true     # if redis down, accept request and warn

# Backend registry
BACKENDS_CONFIG=/app/backends.yaml

# Health checks
BACKEND_HEALTH_INTERVAL_SECONDS=30
BACKEND_UNHEALTHY_THRESHOLD=3
```

## docker-compose orchestration

`docker-compose.yml` at repo root uses profiles. Default `basic` profile starts gateway + redis + tenant store; LLM backends are separate profiles.

```yaml
# basic-infra/docker-compose.yml
version: "3.9"

x-common-env: &common-env
  TZ: Europe/Moscow

services:
  gateway:
    profiles: ["basic"]
    build:
      context: ./llm/gateway
    container_name: basic-infra-gateway
    environment:
      <<: *common-env
      # ...
    ports:
      - "127.0.0.1:8003:8003"
    depends_on:
      redis:
        condition: service_healthy

  redis:
    profiles: ["basic"]
    image: redis:7-alpine
    container_name: basic-infra-redis
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s

  # ─── llama.cpp / T-pro ────────────────────────────────────────────
  tpro-backend-gpu:
    profiles: ["llm-gpu"]
    image: ghcr.io/ggml-org/llama.cpp:server-cuda
    container_name: basic-infra-tpro-gpu
    command: >
      -m /models/T-pro-it-2.1-Q8_0.gguf
      --host 0.0.0.0 --port 8080
      -c 4096 --n-gpu-layers 24
    volumes:
      - ${LLM_MODELS_DIR:-/home/vams/llm-models}:/models
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]

  tpro-backend-cpu:
    profiles: ["llm-cpu"]
    image: ghcr.io/ggml-org/llama.cpp:server
    container_name: basic-infra-tpro-cpu
    command: >
      -m /models/T-pro-it-2.1-Q8_0.gguf
      --host 0.0.0.0 --port 8080
      -c 8192 -t ${TPRO_CPU_THREADS:-8}
    volumes:
      - ${LLM_MODELS_DIR:-/home/vams/llm-models}:/models

  # ─── TEI embed/rerank ─────────────────────────────────────────────
  tei-embed:
    profiles: ["llm-cpu", "llm-gpu"]
    image: ghcr.io/huggingface/text-embeddings-inference:cpu-latest
    container_name: basic-infra-tei-embed
    command: ["--model-id", "BAAI/bge-m3"]
    volumes:
      - ${LLM_MODELS_DIR:-/home/vams/llm-models}:/data
    environment:
      HF_HOME: /data/hf-cache

  tei-rerank:
    profiles: ["llm-cpu", "llm-gpu"]
    image: ghcr.io/huggingface/text-embeddings-inference:cpu-latest
    container_name: basic-infra-tei-rerank
    command: ["--model-id", "BAAI/bge-reranker-v2-m3"]
    volumes:
      - ${LLM_MODELS_DIR:-/home/vams/llm-models}:/data
    environment:
      HF_HOME: /data/hf-cache

volumes:
  models-cache:
    name: basic-infra-models-cache
```

Make targets:

```
make up           docker compose --profile basic --profile llm-gpu up -d  (or llm-cpu)
make down         docker compose down
make logs         docker compose logs -f
make status       curl http://localhost:8003/ready | jq
make test         pytest llm/tests/
make tenants-seed scripts/seed-tenants.py
```

## Tenant CLI

A small command bundled with the gateway:

```bash
basic-infra tenant create --id telcoss --display "Telcoss" --models "*"
# → prints generated api_key — capture it once, store securely

basic-infra tenant list
# → table: id, display, models, created_at

basic-infra tenant rotate-key telcoss
# → new key, old valid 24h

basic-infra tenant delete telcoss --confirm
# → archives (sets deleted_at), does not hard-delete

basic-infra tenant smoke-test telcoss
# → uses the tenant's key to hit /health and /v1/models, reports
```

## Models — file system layout

Models live under a host bind path, default `${HOME}/llm-models/`:

```
/home/vams/llm-models/
├── T-pro-it-2.1-Q8_0.gguf       # ~7 GB
├── bge-m3/                       # checkpoint directory
├── bge-reranker-v2-m3/           # checkpoint directory
└── hf-cache/                     # TEI/HF download cache
```

Initial migration: from `~/PAMYAT-NARODA-GRAPH/models/` to `~/llm-models/` happens in Phase 2 of the tasklist. After migration, both `basic-infra` and (eventually) `pamyat-naroda` bind-mount the new path.

`basic-infra/models/README.md` documents this layout for ops.

## Python SDK contract (`vams-llm-client`)

```python
from vams_llm_client import LlmClient

client = LlmClient.from_env()           # reads LLM_PROVIDER, LLM_BASE_URL, LLM_API_KEY

# Chat (OpenAI-style)
resp = client.chat.completions.create(
    model="t-pro-it-2.1-q8",            # or semantic alias: "default-chat"
    messages=[{"role": "user", "content": "..."}],
    response_format={
        "type": "json_schema",
        "json_schema": {"name": "manhole", "schema": {...}, "strict": True},
    },
)
# resp.choices[0].message.content (parsed JSON if response_format used)

# Embeddings
emb = client.embeddings.create(model="bge-m3", input=["text1", "text2"])
# emb.data[0].embedding -> list[float]

# Rerank (Cohere-style helper)
ranked = client.rerank(
    model="bge-reranker-v2-m3",
    query="...",
    documents=["d1", "d2", ...],
    top_n=5,
)

# Capabilities check
caps = client.capabilities()    # {"chat": True, "embed": True, "rerank": True}

# Optional embedding cache
client.embeddings.cache_enabled = True   # uses LLM_CACHE_DIR
```

Provider implementations live in `client-sdks/python/vams_llm_client/providers/`:
- `basic_infra.py` — thin HTTP wrapper around the platform
- `openai.py` — uses `openai-python` package under the hood
- `anthropic.py` — uses `anthropic` package, translates `response_format` to native tool_use pattern

## Migration paths from existing projects

### pamyat-naroda — what changes

1. **Remove from `pamyat-naroda-graph/docker-compose.yml`:**
   - `llm-gateway`, `retrieval`, `reranker`, `tpro-backend-cpu`, `tpro-backend-gpu` services
   - `pamyat-naroda-graph_faiss_data` volume — stays (it's pamyat's own data, not infra)

2. **Add to project deps**: `vams-llm-client` package.

3. **Code changes** — wherever there was an HTTP client to `llm_gateway:8003`:
   ```python
   # before
   resp = httpx.post("http://llm_gateway:8003/v1/chat/completions", json=...)
   
   # after
   from vams_llm_client import LlmClient
   client = LlmClient.from_env()
   resp = client.chat.completions.create(...)
   ```

4. **`/analyze` endpoint** — that was a domain-specific pamyat endpoint. It moves into pamyat's own code as an in-process function or pamyat-specific service. Composed of: `client.chat.completions.create(...)` + pamyat's prompt + its post-processing.

5. **Retrieval & reranking** — pamyat's `pn_retrieval` service handled both vector search (in faiss) AND embedding. Split it:
   - Pamyat keeps its own faiss index and retrieval orchestration code
   - Embedding calls go through `client.embeddings.create(...)`
   - Rerank calls go through `client.rerank(...)`

6. **env update:**
   ```bash
   LLM_PROVIDER=basic-infra
   LLM_BASE_URL=http://host.docker.internal:8003/v1
   LLM_API_KEY=<from "basic-infra tenant create" output>
   ```

### telcoss — what changes

1. **In `telcoss/src/telcoss/pdf_intake/infrastructure/adapters/`:**
   - `vllm_generation.py` — refactor to use `vams_llm_client.LlmClient.chat.completions`
   - `tei_embedding.py` — refactor to use `client.embeddings`
   - `tei_reranking.py` — refactor to use `client.rerank`

2. **Telcoss `docker-compose.yml`** — no LLM services to remove (telcoss never actually ran vLLM locally; it was mocked in tests). Just add `LLM_*` env vars.

3. **`tests/integration/pdf_intake/`** — fixtures previously mocked vLLM. Keep them mocked for CI; add a separate `tests/e2e/llm/` that runs against real `basic-infra` (manual / nightly, not on every PR).

4. **Close the LLM-task from PR #3** — Phase 7 of the tasklist runs `telcoss pdf-intake extract` against the live platform for `yurlovo-nss-rd.pdf`, asserts Manholes extracted.

## What's NOT in this spec (out of scope for Week 4)

- Storage primitives (Postgres, Redis as shared service for projects, MinIO)
- Observability stack (Prometheus, Loki, Grafana)
- Streaming responses
- Function calling / tool use beyond `response_format`
- Multimodal (image, audio)
- Fine-tuning
- MCP server wrapping the platform

These are roadmapped per ADR-0001 § "Out of scope for Week 4" and queued for Weeks 5–7.
