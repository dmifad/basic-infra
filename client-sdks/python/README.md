# vams-llm-client

Provider-agnostic Python client SDK for the basic-infra LLM platform.

Reference: ADR-0004 (provider switching).

## Install

Consumed by sibling projects as a Poetry path dependency:

```bash
poetry add ../basic-infra/client-sdks/python
```

Cloud providers are optional extras:

```bash
poetry add "../basic-infra/client-sdks/python" --extras "openai anthropic"
```

## Usage

```python
from vams_llm_client import LlmClient

client = LlmClient.from_env()       # reads LLM_PROVIDER, LLM_BASE_URL, LLM_API_KEY

resp = client.chat.completions.create(
    model="t-pro-it-2.1-q8",        # or the semantic alias "default-chat"
    messages=[{"role": "user", "content": "Привет"}],
)

emb = client.embeddings.create(model="bge-m3", input=["text"])
ranked = client.rerank(model="bge-reranker-v2-m3", query="...", documents=[...])
```

Switch provider with one env var — `LLM_PROVIDER=openai` or `anthropic` — no
code changes. `client.capabilities()` reports what the active provider supports.

## Status

Implemented in Phase 6 of Week 4. This package is a stub until then.
