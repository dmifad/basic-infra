# Client integration — telcoss

How `telcoss` consumes the basic-infra LLM platform (Week 4, Phase 7).

## What changed

telcoss's `pdf-intake` bounded context had three infrastructure adapters
talking to vLLM / TEI directly. They now route through the platform via
`vams-llm-client`, keeping their `Port` interfaces unchanged so use cases and
tests are untouched.

| Adapter | Before | After |
|---------|--------|-------|
| `vllm_generation.py` | `AsyncOpenAI` → vLLM | `LlmClient.chat.completions` |
| `tei_embedding.py` | `httpx` → TEI `/embed` | `LlmClient.embeddings` |
| `tei_reranking.py` | `httpx` → TEI `/rerank` | `LlmClient.rerank` |

- The SDK is synchronous; the async adapters call it via `asyncio.to_thread`.
- Structured extraction switched from vLLM's `guided_json` to the platform's
  `response_format={"type":"json_schema",...}`; the free-form fallback stays.
- Wiring (`presentation/dependencies.py`, `pdf_intake/cli.py`) builds one
  `LlmClient.from_env()`.

## Dependency

`vams-llm-client` is a Poetry path dependency on `../basic-infra/client-sdks/python`.
telcoss has `package-mode = false`, so install it editable into the poetry env:

```bash
poetry run pip install -e /home/vams/basic-infra/client-sdks/python --no-deps
```

## Configuration (`.env`)

telcoss runs on the host, so it reaches the platform on the published port:

```bash
LLM_PROVIDER=basic-infra
LLM_BASE_URL=http://localhost:8013/v1
LLM_API_KEY=<~/secrets/basic-infra/telcoss.key>
```

## Verification

- `tests/unit` + `tests/integration` — 332 tests, green (Port-level fakes,
  unaffected by the adapter swap).
- `tests/e2e/llm/test_real_extraction.py` (`@pytest.mark.live`) — exercises all
  three adapters against a live platform. Run:
  ```bash
  LLM_PROVIDER=basic-infra LLM_BASE_URL=http://localhost:8013/v1 \
    LLM_API_KEY=$(cat ~/secrets/basic-infra/telcoss.key) \
    poetry run pytest -m live tests/e2e/llm
  ```

This closes the open LLM-task from PR #3 — extraction runs end-to-end against
basic-infra (T-pro Q8 + BGE-M3 + BGE-Reranker-v2-m3).
