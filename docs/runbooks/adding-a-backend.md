# Runbook — adding a backend

How to register a new model or a new backend engine. Reference: ADR-0005.

## Add a new model to an existing backend kind

1. Edit `llm/backends.yaml` — add a `models:` entry under the relevant backend:
   ```yaml
   - id: my-new-model            # platform-facing id (version-pinned, no `latest`)
     backend_model_name: ...     # the backend's native model name
     capabilities: [chat, structured]
   ```
2. Restart the gateway: `make restart` (or `docker compose restart gateway`).
3. Confirm: `curl -H "Authorization: Bearer $KEY" http://localhost:8013/v1/models | jq`.

The registry validates `backends.yaml` on load — an unknown `kind`, a duplicate
model id, or a malformed entry fails startup loudly (`RegistryError`).

## Add a new backend kind

1. Implement an adapter in `llm/gateway/app/backends/<kind>.py` subclassing
   `BackendAdapter`. Set `kind` and `capabilities`; override the operations the
   backend serves (`chat_completion`, `embedding`, `rerank`, `completion`) and
   `health()`. Use `self._request_json(...)` for backend HTTP — it maps
   transport failures to the right gateway errors (503/504/400).
2. Register the kind in `routing/registry.py` → `_ADAPTER_KINDS`.
3. Add the backend service to `docker-compose.yml` (a fragment under
   `llm/compose/`) and a `backends:` entry in `llm/backends.yaml`.
4. Restart the stack.

No other gateway code changes — the router dispatches by `kind`.

## Health

The background `HealthChecker` probes every adapter every
`BACKEND_HEALTH_INTERVAL_SECONDS`. A backend is marked unhealthy after
`BACKEND_UNHEALTHY_THRESHOLD` consecutive failed probes; the router then fails
fast on it (503) and `/ready` returns 503. A single success clears the streak.
