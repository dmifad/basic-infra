# basic-infra LLM gateway — container image.

FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    POETRY_VIRTUALENVS_CREATE=false \
    POETRY_NO_INTERACTION=1 \
    PYTHON_KEYRING_BACKEND=keyring.backends.null.Keyring

WORKDIR /app

RUN pip install --no-cache-dir "poetry==1.8.2"

# Dependency layer — cached independently of application source.
COPY pyproject.toml poetry.lock* ./
RUN poetry install --only main --no-root

# Application source.
COPY app ./app

EXPOSE 8003

HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=5 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8003/health')"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8003"]
