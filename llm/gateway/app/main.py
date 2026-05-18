"""basic-infra LLM gateway — FastAPI entry point.

See:
    docs/adr/0001-platform-charter.md
    docs/adr/0002-api-contract.md
    docs/specs/llm-platform-spec.md
"""
from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI

# from .api.v1 import chat, completions, embeddings, rerank, models, tenants
# from .config import Settings
# from .routing.registry import Registry
# from .routing.health import HealthChecker
# from .tenancy.store import TenantStore


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Startup/shutdown — load registry, start health checker, open DBs.

    TODO(week4-phase-3): implement.
        - Load Settings from env
        - Open TenantStore (SQLite)
        - Load Registry from backends.yaml
        - Start HealthChecker background task
        - Yield
        - On shutdown: cancel health task, close DBs.
    """
    raise NotImplementedError("week4-phase-3: implement lifespan")


def create_app() -> FastAPI:
    """Application factory.

    TODO(week4-phase-3): implement.
        - Configure structlog
        - Build FastAPI(lifespan=lifespan, title="basic-infra LLM gateway", version="0.1.0")
        - Mount /v1 routers
        - Mount /health, /ready
        - Register exception handlers (OpenAI-style error envelope)
    """
    raise NotImplementedError("week4-phase-3: implement create_app")


app = None  # set by `uvicorn llm.gateway.app.main:app` after create_app is implemented
