# ADR-0003: Multi-tenancy

**Status:** Accepted
**Date:** 2026-05-18

## Context

The platform serves multiple projects (tenants) from the author's ecosystem: `telcoss`, `pamyat-naroda`, future. They share GPU/CPU compute and downloaded models but must not interfere with each other:

- One tenant's burst should not starve another.
- One tenant's misconfigured retry should not hammer the backend on behalf of all.
- Tenants should be identifiable in logs and metrics.
- Each tenant should access only the models it's entitled to (optional, but useful).

This is **not multi-customer SaaS**. It is **multi-project ecosystem within one author's control**. Auth simpler than enterprise; isolation focused on operational fairness.

## Decision

### Tenant model

A tenant is a logical project. Each tenant has:

```
tenant_id:      stable string, lowercase-kebab     ("telcoss", "pamyat-naroda")
api_key:        opaque secret, 32+ random chars    ("tnk_live_<random>")
display_name:   human-friendly                     ("Telcoss")
allowed_models: list of model_ids or "*"           (["t-pro-it-2.1-q8", "bge-m3"] or ["*"])
rate_limits:    per-endpoint dict                  ({"chat.completions": "60/min", "embeddings": "1000/min"})
created_at, updated_at
```

Tenant config lives in a small SQLite database `tenants.db` inside the platform. SQLite is sufficient — write rate is "one tenant per quarter," reads are cached in-memory. No need for Postgres dependency just for this.

### Authentication

`Authorization: Bearer <api_key>` header. The platform looks up `api_key` in tenant table, attaches the resolved `tenant_id` to the request context.

```http
POST /v1/chat/completions HTTP/1.1
Authorization: Bearer tnk_live_abc123...
Content-Type: application/json

{"model": "t-pro-it-2.1-q8", "messages": [...]}
```

Optional convenience: `X-Tenant-ID: telcoss` header. If present, must match the tenant resolved from the API key — else 403. This lets tenants self-identify in logs without relying on key→tenant lookup.

### Rate limiting

Token-bucket per `(tenant_id, endpoint)`. Implemented with Redis (the platform's own Redis container, used for nothing else; if Redis is unavailable, rate limit fails open — log a warning, accept request).

Defaults if not set per tenant:

| Endpoint              | Limit       |
| --------------------- | ----------- |
| chat.completions      | 60 / min    |
| completions           | 60 / min    |
| embeddings            | 1000 / min  |
| rerank                | 200 / min   |
| models (GET)          | unlimited   |

Exceeded → `429 Too Many Requests`, header `Retry-After: <seconds>`.

### Model access control

If `allowed_models = ["*"]` — tenant can use any registered model. If a list — only those. Useful for cost-bearing models (if/when we add a paid cloud backend).

In Week 4: both tenants get `["*"]`. The mechanism exists for future use.

### Tenant CLI

```bash
basic-infra tenant create --id telcoss --display "Telcoss" --models "*"
basic-infra tenant list
basic-infra tenant show telcoss
basic-infra tenant rotate-key telcoss   # generates new api_key, old one valid for 24h grace period
basic-infra tenant delete telcoss       # archives, does not remove (audit trail)
```

### What the platform logs per request

Every request emits one structured log line:

```json
{
  "ts": "2026-05-18T10:30:21.123Z",
  "tenant_id": "telcoss",
  "method": "POST",
  "path": "/v1/chat/completions",
  "model": "t-pro-it-2.1-q8",
  "status": 200,
  "duration_ms": 1247,
  "input_tokens": 856,
  "output_tokens": 312,
  "backend": "llama_cpp",
  "request_id": "req_xyz789"
}
```

### Security boundaries

**Within the trust boundary** (Week 4 scope):
- All clients are author's own projects on author's machine
- The platform binds to `127.0.0.1`, not a public interface
- Bearer tokens in plain HTTP are acceptable on `localhost`
- No CORS, no encryption-in-transit

**Outside the trust boundary** (not Week 4):
- Remote access requires HTTPS + proper auth (OAuth2 / OIDC / mTLS)
- Public exposure requires WAF, audit logging, secret rotation policies
- These are out of scope. If/when needed — see future ADR-0010.

## Consequences

### Positive

- Tenants are identifiable in every log entry.
- Rate-limit blast radius is bounded per tenant.
- Auth is trivial to integrate from client side (one header).
- No premature complexity (no OAuth, no JWT, no signing).

### Negative

- API keys in env files — typical operational risk. Mitigated by `localhost`-only binding.
- SQLite for tenant config — single-writer, fine at this scale, not at high tenant churn.
- Rate limit fails open on Redis outage — accepting requests when we should reject. Trade-off: would rather accept some legitimate traffic than reject all of it during a Redis blip.

## Related decisions

- ADR-0001 (charter)
- ADR-0002 (contract — endpoints that get rate-limited)
- ADR-0005 (backend — tenant access to specific backends, not just models)
