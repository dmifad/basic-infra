# ADR-0004: Provider switching (client-side)

**Status:** Accepted
**Date:** 2026-05-18

## Context

Per ADR-0001, projects should not be locked into the local `basic-infra` platform. They should be able to switch to a cloud LLM provider (OpenAI, Anthropic, future Russian cloud LLM) without changing project source code.

This decision concerns **the client side** — how a project configures which provider it talks to. The platform itself (ADR-0005) is a separate concern about how it talks to backends.

## Decision

### Client SDK provides provider abstraction

A tiny Python package `vams-llm-client` distributed as part of `basic-infra`. Each consuming project depends on it via Poetry. The SDK reads environment variables and dispatches to the right provider:

```python
from vams_llm_client import LlmClient

client = LlmClient.from_env()        # reads env vars
response = client.chat.completions.create(
    model="t-pro-it-2.1-q8",
    messages=[{"role": "user", "content": "..."}],
)
```

Project code does not import `openai`, `anthropic`, or `httpx` directly. It imports only `vams_llm_client`.

### Provider selection via environment

```bash
# Local basic-infra (default)
LLM_PROVIDER=basic-infra
LLM_BASE_URL=http://localhost:8003/v1
LLM_API_KEY=tnk_live_...

# OpenAI cloud
# LLM_PROVIDER=openai
# LLM_API_KEY=sk-...
# (LLM_BASE_URL defaults to OpenAI's URL when provider=openai)

# Anthropic cloud
# LLM_PROVIDER=anthropic
# LLM_API_KEY=sk-ant-...
```

Model IDs map per provider via a config table inside the SDK (or override via env):

```python
# Default mapping in SDK
PROVIDER_MODEL_MAP = {
    "basic-infra": {
        "default-chat":  "t-pro-it-2.1-q8",
        "default-embed": "bge-m3",
        "default-rerank": "bge-reranker-v2-m3",
    },
    "openai": {
        "default-chat":  "gpt-4o-mini",
        "default-embed": "text-embedding-3-small",
        # no native rerank on OpenAI
    },
    "anthropic": {
        "default-chat":  "claude-haiku-4-5",
        # no native embed/rerank on Anthropic
    },
}
```

Projects can request semantic models (`default-chat`) or specific ones (`t-pro-it-2.1-q8`). If a specific model is asked of a provider that doesn't have it — SDK raises `ModelNotAvailable`, fast and explicit.

### Capability advertisement

Not every provider supports every capability:

| Capability    | basic-infra | OpenAI | Anthropic |
| ------------- | ----------- | ------ | --------- |
| chat          | ✅          | ✅     | ✅        |
| embeddings    | ✅          | ✅     | ❌        |
| rerank        | ✅          | ❌     | ❌        |
| structured    | ✅          | ✅     | ✅        |

The SDK exposes `client.capabilities()` → `{"chat": True, "embed": True, "rerank": False}` for the current provider. Project code that needs rerank but is configured against Anthropic gets a clear error at construction time, not at runtime.

### Per-call provider override

Optional:

```python
# Override provider for a specific call
response = client.chat.completions.create(
    model="default-chat",
    messages=[...],
    provider="openai",   # one-off, e.g. for A/B
)
```

This is for development and experimentation. Production code should configure via env, not per-call.

### Graceful degradation

If the local platform is unreachable (`LLM_PROVIDER=basic-infra` but connection refused), the SDK does not silently fail over to cloud. It raises a clear error so the developer fixes the platform.

Rationale: silent fallback to cloud could leak data the developer expected to stay local — privacy footgun. Explicit fallback policies (if any) live in project code, not SDK defaults.

### Caching

The SDK ships an opt-in cache for `embeddings` calls (the most cache-friendly endpoint). Backed by local SQLite, keyed by `(provider, model, text-sha256)`. Off by default; enabled via `LLM_CACHE_DIR=~/.cache/vams-llm`.

Chat completions are not cached by default (variability is the point).

## Consequences

### Positive

- Projects are provider-portable. Same code runs against local or cloud.
- Capabilities check at startup catches misconfiguration immediately.
- Semantic model aliases (`default-chat`) decouple project code from specific model IDs.
- Embedding cache reduces cloud cost for projects that re-embed similar text often.

### Negative

- One more package to maintain (`vams-llm-client`). Acceptable cost — it's thin (< 1000 LOC expected).
- Per-call provider override is a foot-gun (could confuse logs/metrics). Mitigation: log a warning when used.
- Model alias mapping is opinionated. If a project disagrees, it must override explicitly.

## Related decisions

- ADR-0001 (charter — projects must be portable)
- ADR-0002 (contract — what the SDK speaks to basic-infra)
- ADR-0005 (backend pluggability — platform-side counterpart)
