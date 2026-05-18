# ADR-0002: API contract — OpenAI-compatible plus extensions

**Status:** Accepted
**Date:** 2026-05-18

## Context

The platform exposes generation, embeddings, and reranking to client projects. The contract needs to be stable, widely supported (so client SDKs already exist), and not invent unnecessary novelty.

The existing `pn_llm_gateway` is already OpenAI-compatible for chat completions (`/v1/chat/completions`, `/v1/models`). We extend in that direction.

## Decision

### Primary contract: OpenAI-compatible

The platform exposes a subset of the OpenAI API. Standard endpoints:

```
POST  /v1/chat/completions
POST  /v1/completions            (legacy text completion, optional but useful)
POST  /v1/embeddings
GET   /v1/models
```

Rationale: every Python LLM library (openai-python, langchain, llama-index, dspy, instructor) talks OpenAI out of the box. Clients of the platform pay zero integration cost. When in doubt about a parameter, behavior, or error shape — we match OpenAI.

### Reranking — Cohere-style, not OpenAI

OpenAI does not have a reranking endpoint. Cohere's `POST /v1/rerank` is the de-facto standard. We adopt it verbatim:

```http
POST /v1/rerank
{
  "model": "bge-reranker-v2-m3",
  "query": "what is the regulatory deadline for SORM compliance?",
  "documents": ["doc1 text...", "doc2 text...", ...],
  "top_n": 5,
  "return_documents": true
}
```

Response:
```json
{
  "results": [
    {"index": 2, "relevance_score": 0.94, "document": {"text": "..."}},
    {"index": 0, "relevance_score": 0.71, "document": {"text": "..."}},
    ...
  ],
  "model": "bge-reranker-v2-m3"
}
```

### Structured output: `response_format` extension

OpenAI's `response_format` parameter is supported. Two modes:

```json
// Mode 1: free-form JSON
{"response_format": {"type": "json_object"}}

// Mode 2: schema-constrained (recommended)
{"response_format": {
    "type": "json_schema",
    "json_schema": {
        "name": "extracted_manhole",
        "schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "coordinates": {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2},
                ...
            },
            "required": ["name"]
        },
        "strict": true
    }
}}
```

Implementation: forwarded to the backend's guided-decoding facility (`json_schema` in llama.cpp via grammar, `guided_json` in vLLM via outlines/xgrammar). If the backend cannot honor the constraint, the platform falls back to free-form JSON with post-validation against the schema and returns `response_format_fallback: true` in the response metadata (a vendor-extension field).

### Model identifiers

Models exposed via `/v1/models` use semantic, version-pinned IDs:

```
t-pro-it-2.1-q8       (T-pro 2.1, Q8 quantization)
t-pro-it-2.1-fp8      (T-pro 2.1, FP8 — GPU-only)
bge-m3                (BGE-M3 multilingual embeddings)
bge-reranker-v2-m3    (BGE Reranker v2 m3)
```

No `latest` alias is exposed by default. Clients must pin model IDs explicitly so a backend upgrade does not silently change behavior. If a client wants "current default for tenant X", that mapping lives on the client side or in tenant config — not as a server-side alias.

### Errors

OpenAI-style error envelope:

```json
{
  "error": {
    "message": "Model not found: t-pro-it-2.1-fp16",
    "type": "invalid_request_error",
    "code": "model_not_found",
    "param": "model"
  }
}
```

HTTP status codes: 400 (bad request), 401 (auth), 403 (forbidden / tenant has no access to model), 429 (rate limit), 500 (server error), 502/503 (backend unavailable), 504 (backend timeout).

### Operational endpoints

```
GET   /health                Liveness, always 200 if process is up
GET   /ready                 Readiness, 200 only if backends reachable
GET   /metrics               Prometheus exposition (added in Week 6)
GET   /v1/tenants/me         Current tenant identity (for SDK debugging)
```

### What we deliberately do NOT support

- **Streaming** in v1. SSE adds complexity (proxy buffering, client SDK quirks). Most workloads (PDF extraction, batch processing) tolerate non-streaming responses. Will add in Week 5+ if needed.
- **Function calling** (`tools`/`tool_choice`) in v1. Local LLMs vary widely in tool-calling quality. Clients that need tools should use structured output (`response_format`) instead.
- **File upload** in v1. Multimodal arrives if/when needed.
- **Fine-tuning endpoints**. Out of scope per ADR-0001.

## Consequences

### Positive

- Clients use existing OpenAI SDKs unchanged. `openai.Client(base_url="http://localhost:8003/v1", api_key="...")` works.
- Stable, well-understood contract. New developers (or future Claude Code sessions) understand it without reading platform-specific docs.
- Backend swappable transparently: as long as a new backend can serve OpenAI-compat, it slots in.

### Negative

- Reranking is Cohere-style, not OpenAI-style — mild contract impurity. Acceptable trade-off, since OpenAI does not have an equivalent and Cohere's is the standard.
- Vendor extensions (`response_format_fallback`) are not officially OpenAI. Documented as platform-specific in `docs/api/openapi.yaml`.

## Related decisions

- ADR-0001 (charter)
- ADR-0003 (multi-tenancy — authentication and rate limit headers ride on top of this contract)
- ADR-0005 (backend pluggability — backends must satisfy this contract)
