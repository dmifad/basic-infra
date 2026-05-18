# ADR-0001: basic-infra platform — charter

**Status:** Accepted
**Date:** 2026-05-18
**Repository:** `basic-infra` (new, separate git)

## Context

The author runs a personal ecosystem of side-projects. Two are active: `pamyat-naroda-graph` (genealogical archive over WWII records) and `telcoss` (Russian fixed-line ISP operational platform). Both need LLM, both need similar storage primitives. A third project is likely.

Today each project ships its own LLM/storage stack inside its own `docker-compose.yml`. This duplicates infrastructure, wastes GPU cycles (the same model loaded twice in memory), and prevents shared improvements (a fix to the LLM gateway in one project does not benefit the other).

The goal is to extract shared infrastructure into a single, project-agnostic platform consumed by all projects as HTTP/SDK clients.

## Decision

### What `basic-infra` is

**Shared infrastructure platform** for the author's ecosystem. Provides LLM compute (today), storage primitives (later), observability (later) as services. Projects consume the platform as **clients** via stable HTTP API + Python SDK.

In Week 4 scope: **LLM layer only** (generation, embeddings, reranking). Storage and observability are deferred (Week 5+).

### What `basic-infra` is NOT

- **Not a domain layer.** No business logic about telecom, no business logic about genealogy. Project-specific knowledge stays in project repos.
- **Not a SaaS.** Multi-tenant within the author's own ecosystem (separating telcoss requests from pamyat-naroda requests), but not designed for external customers.
- **Not a model trainer.** Models are consumed from third parties (T-Tech, HuggingFace). Fine-tuning is out of scope until there's a concrete need.
- **Not a vector database.** Vector stores are **project data**, not infrastructure. Each project runs its own Qdrant/etc with its own collections. The platform supplies embeddings, the project stores them.
- **Not a prompt store.** Prompts are project business logic. They live in project source code, version-controlled with project releases.
- **Not a RAG orchestrator.** The platform provides generation/embed/rerank as primitives. RAG pipelines (chunk → embed → search → rerank → prompt) are assembled by clients.

### Layered model

```
                  ┌─────────────────────────────────────────────────┐
                  │  basic-infra platform                            │
                  │  ┌────────────────┐  ┌───────────────────────┐  │
                  │  │   llm          │  │  storage (Week 5+)    │  │
                  │  │   • gateway    │  │  • postgres-multi-db  │  │
                  │  │   • backends   │  │  • redis              │  │
                  │  │   • models     │  │  • minio/s3-compat    │  │
                  │  └────────────────┘  └───────────────────────┘  │
                  └────────────┬──────────────────┬─────────────────┘
                               │                  │
                  ┌────────────┴──────┐  ┌────────┴─────────┐
                  │  telcoss          │  │  pamyat-naroda    │
                  │  (client)         │  │  (client)         │
                  │                   │  │                   │
                  │  own Qdrant       │  │  own Qdrant       │
                  │  own prompts      │  │  own prompts      │
                  │  own RAG logic    │  │  own RAG logic    │
                  └───────────────────┘  └───────────────────┘
```

### Provider switching

A project is **never tied** to local infrastructure. It picks its provider through configuration:

```bash
LLM_PROVIDER=local          # basic-infra hosted locally
# LLM_PROVIDER=openai       # OpenAI API
# LLM_PROVIDER=anthropic    # Anthropic API
# LLM_PROVIDER=cloud-ru     # Russian cloud LLM (if relevant)
```

The Python SDK abstracts the choice. Project code stays identical; only the deployment config differs.

This makes `basic-infra` an **option**, not a lock-in. The author can run everything locally for development, switch a single project to a cloud provider, and the project's source code does not change.

### Multi-tenancy strategy

Tenant = project. Today: two tenants (`telcoss`, `pamyat-naroda`). Tomorrow: more.

Isolation level: **token-based authentication + per-tenant rate limits**. No data partitioning needed at the LLM layer (the LLM is stateless; tenant data lives in tenant's own Qdrant).

Quota tracking is opt-in: a simple usage counter per tenant per day, no billing semantics.

## Consequences

### Positive

- Single LLM stack to maintain (one place to upgrade T-pro, one place to fix a bug).
- Projects boot faster (no LLM containers per project; just a config pointing at the platform).
- Project source code is portable (same code runs against local or cloud LLM).
- The platform grows organically — storage and observability arrive when there's pull, not push.

### Negative

- An extra moving part. If `basic-infra` is down, all dependent projects fail.
  - Mitigation: SDK should support graceful degradation where possible (e.g., return cached embedding result if backend unreachable, fail clearly otherwise).
- Operational risk concentrated. A bad model deploy hits all consumers.
  - Mitigation: models pinned per tenant or per environment, no `latest` aliases by default.
- Network hop adds latency vs in-process LLM. ~10-20 ms per call for HTTP.
  - Mitigation: acceptable for non-interactive workloads (PDF extraction, batch processing). For latency-critical paths (if any), client may be co-located with platform.

### Risks deferred

- Authentication is simple Bearer-token today. If exposed beyond `localhost`, this is not enough — needs proper auth (OAuth2 or short-lived JWT). Out of scope for Week 4; flagged in ADR-0003.
- No formal SLO. Best-effort uptime, no monitoring beyond `/health` initially. Will gain real observability in Week 6 when the observability layer is built.

## Related decisions

- ADR-0002 (API contract): how clients talk to the platform.
- ADR-0003 (multi-tenancy): how tenants authenticate and how isolation works.
- ADR-0004 (provider switching): how clients swap between local and cloud LLMs.
- ADR-0005 (backend pluggability): how the platform itself swaps llama.cpp ↔ vLLM ↔ external API.

## Out of scope for Week 4

- Storage primitives (postgres-multi, redis, blob, vector store)
- Observability stack (Prometheus, Loki, Grafana)
- MCP server for Claude Desktop / Claude Code integration with the platform
- Fine-tuning / training infrastructure
- Cost tracking and billing (the platform is non-commercial)
- High-availability deployment (single-host install only)
