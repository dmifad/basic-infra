"""Конфигурация structlog для basic-infra observability контракта.

Один вызов ``setup_logging(settings)`` настраивает:

- structlog → JSON output в stdout (формат соответствует ADR-0011)
- стандартные процессоры: timestamp, level, exception формат
- автоинъекция contextvars: ``request_id``, ``tenant``
- stdlib logging форвардится через structlog (для совместимости с
  библиотеками, которые используют ``logging``)
"""

from __future__ import annotations

import logging
import sys

import structlog
from structlog.types import EventDict, Processor, WrappedLogger

from basic_infra_observability_client.config import ObservabilitySettings
from basic_infra_observability_client.context import (
    get_request_id,
    get_tenant_override,
)


def _add_service_metadata(settings: ObservabilitySettings) -> Processor:
    """Возвращает processor, который добавляет service/env/tenant в каждое событие."""

    service = settings.service_name
    env = settings.env
    default_tenant = settings.tenant

    def processor(
        logger: WrappedLogger, method_name: str, event_dict: EventDict
    ) -> EventDict:
        event_dict.setdefault("service", service)
        event_dict.setdefault("env", env)
        # tenant: override из contextvar побеждает default из настроек.
        tenant = get_tenant_override() or default_tenant
        if tenant:
            event_dict.setdefault("tenant", tenant)
        return event_dict

    return processor


def _add_request_id(
    logger: WrappedLogger, method_name: str, event_dict: EventDict
) -> EventDict:
    """Подставляет request_id из contextvar, если задан."""
    rid = get_request_id()
    if rid:
        event_dict.setdefault("request_id", rid)
    return event_dict


def _add_trace_context(
    logger: WrappedLogger, method_name: str, event_dict: EventDict
) -> EventDict:
    """Кладёт ``trace_id`` / ``span_id`` текущего OTEL-спана в event_dict.

    Это ОСНОВНОЙ путь log↔trace корреляции для basic-infra: SDK логирует
    через structlog, поэтому trace context инъектируется здесь, в structlog-
    цепочке, ДО JSON-рендера — а не через stdlib ``logging.Filter``. Stdlib
    ``tracing.TraceContextFilter`` оставлен фолбэком для сторонних библиотек,
    которые логируют мимо structlog.

    Ключ — именно ``trace_id`` (32 hex): под него матчится Loki ``derivedFields``
    в Grafana (log → trace). ``span_id`` — 16 hex.

    Опционально и лениво: OpenTelemetry живёт в extra ``tracing``. Если он не
    установлен (базовый SDK без extra) или активного валидного спана нет —
    event_dict не трогаем, поля просто отсутствуют (чистый JSON, без null-шума).
    """
    try:
        from opentelemetry import trace
    except ImportError:  # базовый SDK без extra `tracing` — no-op
        return event_dict

    ctx = trace.get_current_span().get_span_context()
    if ctx is not None and ctx.is_valid:
        event_dict.setdefault("trace_id", format(ctx.trace_id, "032x"))
        event_dict.setdefault("span_id", format(ctx.span_id, "016x"))
    return event_dict


def setup_logging(settings: ObservabilitySettings) -> None:
    """Настраивает structlog согласно контракту ADR-0011.

    Идемпотентен: повторный вызов перезаписывает конфигурацию.
    """

    # Общие processors для structlog и stdlib logging.
    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        _add_service_metadata(settings),
        _add_request_id,
        _add_trace_context,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
    ]

    if settings.log_format == "json":
        renderer: Processor = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # stdlib logging → форвардится через structlog. Это нужно чтобы
    # сторонние библиотеки (botocore, aiohttp, ...) тоже попадали в
    # единый JSON-output.
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    # Снимаем существующие handlers (idempotency).
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(settings.log_level.upper())


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Возвращает настроенный structlog logger.

    Использование::

        log = get_logger(__name__)
        log.info("document received", document_id=doc.id, size_bytes=len(data))
    """
    return structlog.stdlib.get_logger(name)
