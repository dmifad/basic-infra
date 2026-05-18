# basic-infra LLM gateway

FastAPI service implementing the OpenAI-compatible LLM gateway for the
basic-infra platform.

- API contract: `docs/api/openapi.yaml`
- Architecture: ADR-0002 (contract), ADR-0003 (tenancy), ADR-0005 (backends)

## Layout

```
app/
├── main.py            FastAPI app, lifespan, route mount
├── config.py          Pydantic Settings
├── api/               HTTP layer — routes + auth dependency
├── routing/           registry, model→backend dispatch, health checks
├── backends/          backend adapters (openai_compat, tei, ...)
├── tenancy/           SQLite tenant store, auth, rate limit, CLI
├── schemas/           Pydantic v2 request/response models
└── observability/     structured logging, metrics stubs
```

## Develop

```bash
poetry install
poetry run pytest
poetry run ruff check .
poetry run mypy .
```

Implemented across Phases 3–4 of Week 4.
