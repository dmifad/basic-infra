# Client integration — pamyat-naroda

How `pamyat-naroda-graph` consumes the basic-infra LLM platform (Week 4, Phase 6).

## What changed

pamyat ran its own `llm-gateway`, `reranker` and `tpro-backend` services. All
three are removed; LLM work now goes through the platform.

- **`/analyze`** — was a domain endpoint in the standalone `llm-gateway`
  service. Relocated to `services/worker/app/analysis/` as an in-process
  `run_analysis()` the worker calls directly; the LLM completion goes through
  the SDK.
- **`analyze_run.py`** (worker task) — rerank via `client.rerank()`; analysis
  via the in-process `run_analysis()` (no more HTTP to `llm-gateway`/`reranker`).
- **`retrieval`** — kept (it owns the FAISS index). Its embedding step now
  calls `client.embeddings`; the local BGE-M3 load and `FlagEmbedding`/`torch`
  are gone (the `retrieval` image dropped from 6.1 GB to 715 MB).

## Dependency

pamyat uses pip + per-service `requirements/`, not Poetry path deps. The SDK is
**vendored** into `shared/vams_llm_client/` — the worker and retrieval
Dockerfiles already `COPY shared/`, so no Dockerfile or requirements change is
needed (the SDK's runtime deps, httpx + pydantic, are already in `base.txt`).

## Connectivity

pamyat's containers reach the platform over a shared Docker network — the
gateway is **not** exposed to them on a host port (ADR-0003 keeps it on
`127.0.0.1`).

```bash
docker network create basic-infra-net      # once
```

basic-infra's gateway joins `basic-infra-net`; pamyat's `worker` and `retrieval`
join it too and reach the gateway as `basic-infra-gateway:8003`.

## Configuration (`.env`)

```bash
LLM_PROVIDER=basic-infra
LLM_BASE_URL=http://basic-infra-gateway:8003/v1
LLM_API_KEY=<~/secrets/basic-infra/pamyat-naroda.key>
```

## Verification

After `docker compose up -d --remove-orphans`, all six pamyat services come up
healthy. `retrieval` and `worker` were confirmed embedding (1024-dim) and
reranking live through the platform over `basic-infra-net`.
