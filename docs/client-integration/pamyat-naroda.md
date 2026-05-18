# Client integration — pamyat-naroda

> **Status:** stub. Filled in Phase 6 with the actual integration patterns used.

How `pamyat-naroda-graph` consumes the basic-infra LLM platform.

Reference: `docs/specs/llm-platform-spec.md` § "Migration paths — pamyat-naroda".

## Summary of changes (planned)

- Remove LLM services from `docker-compose.yml`: `llm-gateway`, `reranker`,
  `retrieval`, `tpro-backend-cpu`, `tpro-backend-gpu`.
- Add `vams-llm-client` as a Poetry path dependency.
- Replace direct HTTP calls to `llm_gateway:8003` with SDK calls.
- `/analyze` (domain-specific) moves into pamyat's own code.
- `pn_retrieval` splits: embedding via SDK, vector search stays internal.
- `.env`: add `LLM_PROVIDER`, `LLM_BASE_URL`, `LLM_API_KEY`.

_TODO(week4-phase-6): concrete diffs, retrieval-split decision, /analyze relocation._
