"""OpenTelemetry distributed tracing for basic-infra client projects.

Part of ``basic_infra_observability_client`` (ADR-0012). Extends the existing
observability surface (metrics + structured logs) with traces so the three
correlate through a shared ``trace_id`` / ``request_id``.

Public surface
--------------
* :class:`TracingSettings` — env-driven config, prefix
  ``BASIC_INFRA_OBSERVABILITY_TRACING_``.
* :func:`setup_tracing` — idempotent global ``TracerProvider`` configuration.
* :func:`instrument_fastapi` / :func:`instrument_sqlalchemy` — opt-in
  auto-instrumentation guarded by extra deps.
* :func:`install_trace_log_correlation` — injects ``trace_id`` / ``span_id``
  into log records so logs shipped to Loki link back to Tempo spans.
* :func:`get_tracer` — convenience accessor.

Design notes
------------
* When ``enabled`` is ``False`` every entry point is a no-op and the global
  OTEL ``ProxyTracerProvider`` (no-op) is left in place. Adoption is therefore
  gradual and unit tests need no live collector.
* ``env`` is read from ``BASIC_INFRA_OBSERVABILITY_TRACING_ENV`` and is kept
  deliberately separate from the application ``ENV`` (no ``AliasChoices``
  unification — same discipline as ADR-0011 §Config).
* The default exporter target is the in-network Tempo OTLP/gRPC endpoint
  ``http://tempo:4317`` (host-published debug ports are shifted — see
  tracing/compose/tracing.yml — but in-network services use the canonical
  container port).
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any, Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_TRACER_NAME = "basic_infra"

# Module-global guard so setup_tracing is idempotent within a process.
#
# NOTE: OpenTelemetry's global TracerProvider can only be *set* once per
# process (a second ``set_tracer_provider`` is silently ignored with a
# warning). We therefore also cache the provider object we built so repeated
# ``setup_tracing`` calls return the identical instance regardless of the OTEL
# global's state.
_configured = False
_provider: "Any" = None


class TracingSettings(BaseSettings):
    """Tracing configuration. Env prefix ``BASIC_INFRA_OBSERVABILITY_TRACING_``."""

    model_config = SettingsConfigDict(
        env_prefix="BASIC_INFRA_OBSERVABILITY_TRACING_",
        extra="ignore",
    )

    enabled: bool = Field(default=False)
    service_name: str = Field(default="unknown-service")
    service_version: Optional[str] = Field(default=None)
    # Explicit deployment-env field; NOT aliased to the app's ENV by design.
    env: str = Field(default="local")
    otlp_endpoint: str = Field(default="http://tempo:4317")
    # gRPC to the in-network collector is insecure (no TLS on the compose net).
    otlp_insecure: bool = Field(default=True)
    sample_ratio: float = Field(default=1.0, ge=0.0, le=1.0)


@lru_cache(maxsize=1)
def get_settings() -> TracingSettings:
    return TracingSettings()


def _build_resource(settings: TracingSettings) -> "Any":
    from opentelemetry.sdk.resources import Resource

    attrs: dict[str, Any] = {
        "service.name": settings.service_name,
        "deployment.environment": settings.env,
    }
    if settings.service_version:
        attrs["service.version"] = settings.service_version
    return Resource.create(attrs)


def _build_sampler(settings: TracingSettings) -> "Any":
    from opentelemetry.sdk.trace.sampling import (
        ALWAYS_ON,
        ParentBased,
        TraceIdRatioBased,
    )

    if settings.sample_ratio >= 1.0:
        return ParentBased(ALWAYS_ON)
    return ParentBased(TraceIdRatioBased(settings.sample_ratio))


def setup_tracing(
    app: Optional["Any"] = None,
    settings: Optional[TracingSettings] = None,
    *,
    span_exporter: Optional["Any"] = None,
    force: bool = False,
) -> "Any":
    """Configure the global ``TracerProvider``. Idempotent.

    Parameters
    ----------
    app:
        Optional FastAPI app to auto-instrument once the provider is live.
    settings:
        Override settings; defaults to env-derived :func:`get_settings`.
    span_exporter:
        Inject a span exporter (tests pass ``InMemorySpanExporter``). When
        ``None`` a real OTLP/gRPC exporter to ``settings.otlp_endpoint`` is
        built.
    force:
        Reconfigure even if already configured (mainly for tests).

    Returns the active ``TracerProvider`` (no-op when disabled).
    """
    global _configured, _provider

    settings = settings or get_settings()

    from opentelemetry import trace

    if not settings.enabled:
        # Leave the default no-op proxy provider in place.
        return trace.get_tracer_provider()

    if _configured and not force:
        return _provider

    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import (
        BatchSpanProcessor,
        SimpleSpanProcessor,
    )

    provider = TracerProvider(
        resource=_build_resource(settings),
        sampler=_build_sampler(settings),
    )

    if span_exporter is not None:
        # Tests / in-memory: export synchronously so spans are visible at once.
        provider.add_span_processor(SimpleSpanProcessor(span_exporter))
    else:
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
            OTLPSpanExporter,
        )

        exporter = OTLPSpanExporter(
            endpoint=settings.otlp_endpoint,
            insecure=settings.otlp_insecure,
        )
        provider.add_span_processor(BatchSpanProcessor(exporter))

    # OTEL only honours the first global provider per process; this is a no-op
    # (with a warning) if something already configured one. We still keep our
    # own reference so callers get the provider whose exporter we wired.
    trace.set_tracer_provider(provider)
    _configured = True
    _provider = provider

    if app is not None:
        instrument_fastapi(app)

    return provider


def get_tracer(name: str = _TRACER_NAME) -> "Any":
    from opentelemetry import trace

    return trace.get_tracer(name)


def instrument_fastapi(app: "Any") -> None:
    """Auto-instrument a FastAPI app. No-op if the extra dep is missing."""
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    except ImportError:  # pragma: no cover - optional extra
        logging.getLogger(__name__).warning(
            "opentelemetry-instrumentation-fastapi not installed; "
            "skipping FastAPI instrumentation"
        )
        return
    FastAPIInstrumentor.instrument_app(app)


def instrument_sqlalchemy(engine: "Any") -> None:
    """Auto-instrument a SQLAlchemy engine. No-op if the extra dep is missing.

    Pass the *sync* engine, or for async engines pass ``engine.sync_engine``.
    """
    try:
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
    except ImportError:  # pragma: no cover - optional extra
        logging.getLogger(__name__).warning(
            "opentelemetry-instrumentation-sqlalchemy not installed; "
            "skipping SQLAlchemy instrumentation"
        )
        return
    SQLAlchemyInstrumentor().instrument(engine=engine)


class TraceContextFilter(logging.Filter):
    """Logging filter injecting current ``trace_id`` / ``span_id`` into records.

    FALLBACK path. The primary log↔trace correlation for basic-infra runs as a
    structlog processor (``logging_setup._add_trace_context``), because the SDK
    logs through structlog. This stdlib ``logging.Filter`` exists for code paths
    that bypass structlog entirely (third-party libs attaching their own
    handlers). Both emit the same ``trace_id`` key the Loki derived field matches.

    Outside any span the fields are set to ``None`` (renders as null in JSON).
    """

    def filter(self, record: logging.LogRecord) -> bool:
        from opentelemetry import trace

        span = trace.get_current_span()
        ctx = span.get_span_context()
        if ctx is not None and ctx.is_valid:
            record.trace_id = format(ctx.trace_id, "032x")
            record.span_id = format(ctx.span_id, "016x")
        else:
            record.trace_id = None
            record.span_id = None
        return True


def install_trace_log_correlation(logger: Optional[logging.Logger] = None) -> None:
    """Attach :class:`TraceContextFilter` to a logger (root by default).

    Idempotent: will not attach a second filter of the same type.
    """
    target = logger or logging.getLogger()
    if any(isinstance(f, TraceContextFilter) for f in target.filters):
        return
    target.addFilter(TraceContextFilter())


def reset_for_tests() -> None:
    """Clear the idempotency guard. Test-only helper.

    Cannot un-set OpenTelemetry's process-global TracerProvider (OTEL forbids
    re-setting it), so tests that assert on recorded spans should use the
    provider object returned by :func:`setup_tracing` rather than the global
    :func:`get_tracer`.
    """
    global _configured, _provider
    _configured = False
    _provider = None
    get_settings.cache_clear()


__all__ = [
    "TracingSettings",
    "get_settings",
    "setup_tracing",
    "get_tracer",
    "instrument_fastapi",
    "instrument_sqlalchemy",
    "TraceContextFilter",
    "install_trace_log_correlation",
    "reset_for_tests",
]
