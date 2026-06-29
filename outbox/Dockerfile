# basic-infra outbox dispatcher — generic transactional-outbox delivery (ADR-0019).
# Build context is the repo root (so the observability SDK is reachable), per the
# compose service. Mirrors the llm/gateway python-slim pattern.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Runtime deps: asyncpg (LISTEN + queries) + the observability SDK's deps.
RUN pip install --no-cache-dir \
    "asyncpg>=0.29" "structlog>=24.1" "pydantic>=2.6" "pydantic-settings>=2.2" \
    "prometheus-client>=0.20"

# Observability SDK is live-sourced from the repo (like other platform services);
# the dispatcher itself carries no consumer specifics.
COPY sdk/basic_infra_observability_client /opt/sdk/basic_infra_observability_client
COPY outbox/basic_infra_outbox /app/basic_infra_outbox

ENV PYTHONPATH=/opt/sdk/basic_infra_observability_client:/app

ENTRYPOINT ["python", "-m", "basic_infra_outbox"]
