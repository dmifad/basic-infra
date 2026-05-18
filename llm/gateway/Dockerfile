# basic-infra LLM gateway — container image
#
# SKELETON — finalized in Phase 5 (live compose bring-up).
# Phase 3/4 implement the app; the build below is the intended shape.

FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    POETRY_VIRTUALENVS_CREATE=false

WORKDIR /app

RUN pip install --no-cache-dir poetry

# Dependency layer (cached independently of source)
COPY pyproject.toml ./
RUN poetry install --only main --no-root --no-interaction || true

# Application source
COPY app ./app

EXPOSE 8003

# TODO(week4-phase-5): finalize entrypoint once app.main:app is implemented.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8003"]
