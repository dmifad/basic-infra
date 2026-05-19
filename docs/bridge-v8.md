# Bridge v8 — end of Week 4

Hand-off context for the next session. Supersedes bridge-v7 (telcoss Week 3).

## What Week 4 produced

`basic-infra` — a shared LLM platform, extracted from `telcoss` and
`pamyat-naroda-graph` and consumed by both as clients.

| Component | State |
|-----------|-------|
| LLM gateway | FastAPI, OpenAI-compatible + Cohere-style rerank, multi-tenant. Live on `127.0.0.1:8013`. |
| Backends | llama.cpp (T-pro Q8), TEI embed (BGE-M3), TEI rerank (BGE-Reranker-v2-m3) — adapter + registry + router + health checks. |
| Tenancy | SQLite store, Argon2 keys, 24 h rotation grace, Redis rate limits. |
| Client SDK | `vams-llm-client` — provider-agnostic (basic-infra / openai / anthropic), opt-in embedding cache. |
| Tests | gateway 72, SDK 19+2, telcoss 332+3 — all green. ruff + mypy-strict clean. |

Commits on `main`: `[week4-phase-1]` … `[week4-phase-8]`.

## Client state

- **telcoss** — branch `migrate-to-basic-infra` off `week3-architecture-package`.
  pdf-intake adapters consume the platform via the SDK; PR #3's LLM-task closed
  by live extraction (`tests/e2e/llm/`). `main` untouched until the branch merges.
- **pamyat-naroda** — branch `migrate-to-basic-infra`. llm-gateway / reranker /
  tpro-backend services removed; `/analyze` in-process; retrieval + worker use
  the SDK over the shared `basic-infra-net` network. `main` untouched.

## Operational notes

- Gateway host port is `8013` (`GATEWAY_HOST_PORT`) while pamyat still holds
  8003; once pamyat's old gateway is gone it can return to 8003.
- `docker network create basic-infra-net` is a prerequisite — the shared
  network for container-to-container client access.
- Tenant keys: `~/secrets/basic-infra/{telcoss,pamyat-naroda}.key`.
- Models live at `~/llm-models/` (bind-mounted; pamyat symlinks to it).

## Remaining / next

- Merge the two `migrate-to-basic-infra` branches after a full client test pass
  (telcoss `make test`; pamyat workflow smoke).
- **Week 5** — Compliance bounded context in telcoss.
- **Week 6** — basic-infra storage layer (Postgres-multi, Redis, MinIO) +
  observability (Prometheus, Loki, Grafana).
- Deferred in v1 (ADR-0002): streaming, function-calling, multimodal.
