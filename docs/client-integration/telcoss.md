# Client integration — telcoss

> **Status:** stub. Filled in Phase 7 with the actual integration patterns used.

How `telcoss` consumes the basic-infra LLM platform.

Reference: `docs/specs/llm-platform-spec.md` § "Migration paths — telcoss".

## Summary of changes (planned)

- `src/telcoss/pdf_intake/infrastructure/adapters/`:
  - `vllm_generation.py` → `vams_llm_client` chat completions
  - `tei_embedding.py`   → `vams_llm_client` embeddings
  - `tei_reranking.py`   → `vams_llm_client` rerank
- `.env`: add `LLM_PROVIDER`, `LLM_BASE_URL`, `LLM_API_KEY`.
- New `tests/e2e/llm/` suite marked `@pytest.mark.live`.

_TODO(week4-phase-7): concrete diffs, env values, e2e command sequence._
