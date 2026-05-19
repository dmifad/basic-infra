"""basic-infra LLM gateway — FastAPI entry point.

See:
    docs/adr/0001-platform-charter.md
    docs/adr/0002-api-contract.md
    docs/specs/llm-platform-spec.md
"""
from __future__ import annotations

import secrets
import time
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .api.v1 import chat, completions, embeddings, models, rerank, tenants
from .config import Settings, get_settings
from .exceptions import GatewayError, InvalidRequestError, RateLimitError
from .observability.logging import configure_logging, get_logger
from .routing.health import HealthChecker
from .routing.registry import Registry
from .routing.router import Router
from .schemas.errors import ErrorDetail, ErrorEnvelope
from .tenancy.auth import Authenticator
from .tenancy.ratelimit import RateLimiter
from .tenancy.store import TenantStore

_log = get_logger("gateway")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Open all platform resources for the app's lifetime, close them on exit.

    Brings up: tenant store, authenticator, rate limiter, backend registry +
    router, and the background health checker.
    """
    settings: Settings = app.state.settings
    store = TenantStore(settings.tenant_db_path)
    app.state.store = store
    app.state.authenticator = Authenticator(store)
    app.state.rate_limiter = RateLimiter(
        settings.redis_url, fail_open=settings.rate_limit_fail_open
    )

    registry = Registry.load(settings.backends_config)
    app.state.registry = registry
    app.state.router = Router(registry)
    health_checker = HealthChecker(
        registry,
        interval_seconds=settings.backend_health_interval_seconds,
        unhealthy_threshold=settings.backend_unhealthy_threshold,
    )
    app.state.health_checker = health_checker
    await health_checker.start()

    _log.info(
        "gateway_startup",
        tenant_db=str(settings.tenant_db_path),
        backends=len(registry.adapters),
    )
    try:
        yield
    finally:
        await health_checker.stop()
        await registry.aclose()
        await app.state.rate_limiter.close()
        store.close()
        _log.info("gateway_shutdown")


def _error_response(exc: GatewayError) -> JSONResponse:
    """Render a :class:`GatewayError` as the OpenAI-style error envelope."""
    envelope = ErrorEnvelope(
        error=ErrorDetail(
            message=exc.message, type=exc.error_type, code=exc.code, param=exc.param
        )
    )
    headers: dict[str, str] = {}
    if isinstance(exc, RateLimitError):
        headers["Retry-After"] = str(exc.retry_after)
    return JSONResponse(
        status_code=exc.status_code, content=envelope.model_dump(), headers=headers
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the FastAPI application.

    Args:
        settings: explicit configuration; if omitted, it is read from the
            environment. Tests pass an explicit ``Settings`` to point at a
            temporary tenant DB and Redis.
    """
    settings = settings or get_settings()
    configure_logging(settings.gateway_log_level, settings.gateway_log_format)

    app = FastAPI(title="basic-infra LLM gateway", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings

    for module in (chat, completions, embeddings, rerank, models, tenants):
        app.include_router(module.router, prefix="/v1")

    @app.get("/health", tags=["ops"])
    async def health() -> dict[str, str]:
        """Liveness — always 200 while the process is up."""
        return {"status": "ok"}

    @app.get("/ready", tags=["ops"])
    async def ready() -> Response:
        """Readiness — 200 only when every registered backend is healthy.

        With no backends registered the gateway is trivially ready.
        """
        registry: Registry = app.state.registry
        adapters = registry.adapters
        backends = [
            {
                "name": adapter.name,
                "healthy": adapter.is_healthy,
                "consecutive_failures": adapter.consecutive_failures,
                "last_checked": (
                    adapter.last_checked.isoformat() if adapter.last_checked else None
                ),
            }
            for adapter in adapters
        ]
        all_ok = all(adapter.is_healthy for adapter in adapters)
        return JSONResponse(
            status_code=200 if all_ok else 503,
            content={"ready": all_ok, "backends": backends},
        )

    @app.exception_handler(GatewayError)
    async def _on_gateway_error(request: Request, exc: GatewayError) -> JSONResponse:
        return _error_response(exc)

    @app.exception_handler(RequestValidationError)
    async def _on_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        errors = exc.errors()
        first = errors[0] if errors else {}
        loc = [str(p) for p in first.get("loc", ()) if p != "body"]
        message = first.get("msg", "Invalid request")
        return _error_response(
            InvalidRequestError(message, param=".".join(loc) or None)
        )

    @app.middleware("http")
    async def request_context(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        """Tag each request with an id and emit one structured log line."""
        request_id = "req_" + secrets.token_hex(8)
        request.state.request_id = request_id
        structlog.contextvars.bind_contextvars(request_id=request_id)
        start = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            _log.info(
                "request",
                method=request.method,
                path=request.url.path,
                status=status,
                duration_ms=round((time.perf_counter() - start) * 1000, 1),
                tenant_id=getattr(request.state, "tenant_id", None),
                model=getattr(request.state, "model", None),
                backend=getattr(request.state, "backend", None),
            )
            structlog.contextvars.clear_contextvars()

    return app


app = create_app()
