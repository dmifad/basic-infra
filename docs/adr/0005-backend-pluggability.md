# ADR-0005: Backend pluggability (platform-side)

**Status:** Accepted
**Date:** 2026-05-18

## Context

ADR-0004 covers how **clients** swap providers. This decision covers how the **platform itself** swaps between backend engines that serve the same OpenAI-compatible contract:

- `llama.cpp` for GGUF models on CPU or GPU (current default — T-pro Q8)
- `vLLM` for high-throughput GPU inference
- `tei` (Text Embeddings Inference) for embeddings/reranking
- External cloud APIs (OpenAI, Anthropic) as fall-through backends

A tenant's request hits the gateway. The gateway routes to a backend. Which backend is chosen is configuration, not source code.

## Decision

### Backend registry

A YAML config at `basic-infra/llm/backends.yaml`:

```yaml
backends:
  - name: llama-cpp-tpro
    kind: openai_compat
    base_url: http://tpro-backend:8080/v1
    models:
      - id: t-pro-it-2.1-q8
        capabilities: [chat, completions, structured]
        backend_model_name: T-pro-it-2.1-Q8_0.gguf
      - id: t-pro-it-2.1-fp8
        capabilities: [chat, completions, structured]
        backend_model_name: T-pro-it-2.1-FP8

  - name: tei-embed
    kind: tei
    base_url: http://tei-embed:80
    models:
      - id: bge-m3
        capabilities: [embeddings]
        backend_model_name: BAAI/bge-m3

  - name: tei-rerank
    kind: tei_rerank
    base_url: http://tei-rerank:80
    models:
      - id: bge-reranker-v2-m3
        capabilities: [rerank]
        backend_model_name: BAAI/bge-reranker-v2-m3

  # Optional external fallbacks — not enabled by default
  # - name: openai-fallback
  #   kind: openai
  #   base_url: https://api.openai.com/v1
  #   api_key_env: OPENAI_API_KEY
  #   models:
  #     - id: gpt-4o-mini
  #       capabilities: [chat, completions, embeddings, structured]
```

`kind` selects the adapter implementation. Adapters:

| Kind            | What it speaks                  | Notes                                       |
| --------------- | ------------------------------- | ------------------------------------------- |
| `openai_compat` | OpenAI API (subset)             | llama.cpp server speaks this. Pass-through. |
| `vllm`          | OpenAI API + vLLM extensions    | guided_json via outlines/xgrammar           |
| `tei`           | Text Embeddings Inference REST  | `/embed` endpoint                           |
| `tei_rerank`    | TEI rerank endpoint             | `/rerank` endpoint                          |
| `openai`        | OpenAI Cloud                    | needs `api_key_env`                         |
| `anthropic`     | Anthropic Cloud                 | translates OpenAI-style → Anthropic native  |

### Router

Routing is `model_id → backend`. The router builds an in-memory map from the registry at startup and on SIGHUP (config reload without restart).

If a tenant requests `model="t-pro-it-2.1-q8"`:
1. Router looks up `t-pro-it-2.1-q8` → backend `llama-cpp-tpro`.
2. Tenancy layer checks `t-pro-it-2.1-q8` is in `allowed_models` for tenant.
3. Request is forwarded to `http://tpro-backend:8080/v1/chat/completions` with original payload.

If the model is unknown — `404 model_not_found`. If a model is registered but the backend is unhealthy — `503 backend_unavailable` (the router runs background health checks every 30s).

### Why not let clients address backends directly

Three reasons:

1. **Authentication.** Tenants have one credential to the platform. Tenants do not know about external API keys (e.g., the platform's OpenAI key, if used). The platform handles secret management.
2. **Observability.** All requests funnel through one logger. Per-tenant usage and latency are uniform.
3. **Backend health and circuit-breaking.** If T-pro is hung, the router can fail fast and (in future) reroute to a fallback. A client addressing the backend directly has no such option.

### Structured output translation

The platform receives `response_format` per OpenAI spec. The adapter translates:

| Backend kind   | How structured output is requested                       |
| -------------- | -------------------------------------------------------- |
| `openai_compat` (llama.cpp) | `json_schema` → llama grammar; or `json_object` → `format: "json"` |
| `vllm`         | `guided_json` parameter                                  |
| `tei` / `tei_rerank` | N/A (not chat)                                     |
| `openai`       | Pass-through native                                      |
| `anthropic`    | `response_format` → `tool_use` workaround                |

If the adapter cannot honor the request — falls back to free-form output + post-validation against the schema. Returns `metadata.response_format_fallback: true` so clients can decide whether to retry or accept.

### Health and readiness

`GET /ready` returns 200 only if **every backend in registry** is healthy. `GET /health` returns 200 if the platform process is alive (does not check backends).

Health-check intervals are per-backend (default 30s). A backend that fails 3 consecutive checks is marked unhealthy; requests routed to it return 503 immediately rather than waiting for timeout.

### Adding a new backend

1. Add an entry to `backends.yaml`.
2. If new `kind` — add adapter in `llm/backends/<kind>.py` implementing the abstract `BackendAdapter` interface.
3. Reload config (SIGHUP or restart).

That's it. No platform code changes for adding new instances of existing kinds.

## Consequences

### Positive

- Adding a new local model: one entry in YAML.
- Adding a new backend kind (e.g., Ollama, vLLM): one adapter class + entry in YAML.
- Tenants never see backends — only models. Backend topology can change without breaking clients.
- Tests can mock adapters per kind; no need to spin up real backends.

### Negative

- YAML config drift risk — entries can be added that have no corresponding adapter, or refer to models the backend doesn't actually serve. Mitigation: startup validation that each registered model is reachable; fail fast if not.
- Adapter layer adds latency (one extra hop, one extra serialization). Acceptable on `localhost`.
- Translation between OpenAI and non-OpenAI backends (Anthropic) is non-trivial and can lose fidelity. Mitigation: log when translation drops fields.

## Related decisions

- ADR-0001 (charter)
- ADR-0002 (the API contract that adapters must satisfy upstream)
- ADR-0003 (multi-tenancy — gates which models a tenant can route to)
- ADR-0004 (client-side provider switching — orthogonal layer)
