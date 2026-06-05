"""basic_infra_observability_client — SDK observability для basic-infra.

Публичный API:

- ``ObservabilitySettings`` — конфигурация из env vars.
- ``setup_logging``, ``get_logger`` — structlog config + logger factory.
- ``setup_metrics`` — инициализация метрик + ``/metrics`` HTTP-сервер.
- ``metrics.counter / gauge / histogram`` — instrument-фабрики с
  автоматическими стандартными лейблами.
- ``request_scope`` / ``tenant_scope`` — контекст-менеджеры.

Базовая адаптация в сервисе::

    from basic_infra_observability_client import (
        ObservabilitySettings,
        setup_logging,
        setup_metrics,
        get_logger,
    )

    settings = ObservabilitySettings()  # читает env
    setup_logging(settings)
    setup_metrics(settings)
    log = get_logger(__name__)
    log.info("service started")
"""

from basic_infra_observability_client import metrics
from basic_infra_observability_client.config import ObservabilitySettings
from basic_infra_observability_client.context import (
    get_request_id,
    get_tenant_override,
    request_scope,
    set_request_id,
    tenant_scope,
)
from basic_infra_observability_client.logging_setup import (
    get_logger,
    setup_logging,
)
from basic_infra_observability_client.metrics import setup_metrics

# Tracing (ADR-0012). Safe to import unconditionally: tracing.py imports
# opentelemetry lazily inside functions, so this does NOT pull the optional
# `tracing` extra into metrics/logs-only consumers. Only calling
# setup_tracing(enabled=True) requires the extra to be installed.
from basic_infra_observability_client.tracing import (
    TraceContextFilter,
    TracingSettings,
    get_tracer,
    install_trace_log_correlation,
    instrument_fastapi,
    instrument_sqlalchemy,
    setup_tracing,
)

__all__ = [
    "ObservabilitySettings",
    "setup_logging",
    "setup_metrics",
    "get_logger",
    "metrics",
    "request_scope",
    "tenant_scope",
    "set_request_id",
    "get_request_id",
    "get_tenant_override",
    # tracing (ADR-0012)
    "TracingSettings",
    "setup_tracing",
    "get_tracer",
    "instrument_fastapi",
    "instrument_sqlalchemy",
    "TraceContextFilter",
    "install_trace_log_correlation",
]

__version__ = "0.1.0"
