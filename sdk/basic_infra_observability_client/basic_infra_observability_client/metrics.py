"""Хелперы для метрик с автоматическими стандартными лейблами.

Контракт лейблов (ADR-0011 §«Контракт метрик»):

- ``service`` — заполняется из настроек, неизменяемо после setup
- ``env`` — заполняется из настроек
- ``tenant`` — из настроек ИЛИ tenant_scope override

Высоко-кардинальные лейблы (``request_id``, ``user_id``, ``document_id``)
**запрещены** на уровне SDK. Если возникает соблазн добавить такой
лейбл — используйте логи (поиск через LogQL), не метрики.

Использование::

    from basic_infra_observability_client import metrics

    documents_received = metrics.counter(
        "pdf_intake_documents_received_total",
        "Total documents received by pdf-intake",
        labels=["source"],  # доп. низко-кардинальные лейблы
    )

    documents_received.labels(source="operator-portal").inc()
"""

from __future__ import annotations

import threading
from typing import Any, Generic, Sequence, TypeVar

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    REGISTRY,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
    start_http_server,
)

from basic_infra_observability_client.config import ObservabilitySettings
from basic_infra_observability_client.context import get_tenant_override


# Глобальное состояние SDK — заполняется в setup_metrics().
_settings: ObservabilitySettings | None = None
_server_started = False
_server_lock = threading.Lock()


# Стандартные лейблы. ``tenant`` опциональный, ``service``/``env``
# заполняются неизменяемо.
_STANDARD_LABELS = ("service", "env", "tenant")


def setup_metrics(
    settings: ObservabilitySettings,
    *,
    start_server: bool = True,
    registry: CollectorRegistry | None = None,
) -> None:
    """Инициализация метрик SDK.

    :param settings: настройки observability.
    :param start_server: если True — запускает HTTP-сервер ``/metrics``
        на ``settings.metrics_port``. Идемпотентен.
    :param registry: альтернативный registry (для тестов). По умолчанию
        — глобальный prometheus_client REGISTRY.
    """
    global _settings, _server_started

    _settings = settings

    if not settings.metrics_enabled or not start_server:
        return

    with _server_lock:
        if _server_started:
            return
        start_http_server(
            settings.metrics_port,
            registry=registry or REGISTRY,
        )
        _server_started = True


def _label_values_for_dimensions(
    extra: dict[str, str] | None,
) -> dict[str, str]:
    """Заполняет стандартные лейблы из settings/context + добавляет extra."""
    if _settings is None:
        raise RuntimeError(
            "setup_metrics() must be called before creating instruments"
        )
    tenant = get_tenant_override() or _settings.tenant or ""
    base = {
        "service": _settings.service_name,
        "env": _settings.env,
        "tenant": tenant,
    }
    if extra:
        base.update(extra)
    return base


# Constrained to the three concrete instrument types so the wrapper preserves
# which one it holds: counter() → _LabelledInstrument[Counter] etc., and
# .labels() returns that concrete type (so .inc()/.observe() type-check downstream).
_M = TypeVar("_M", Counter, Gauge, Histogram)


class _LabelledInstrument(Generic[_M]):
    """Базовая обёртка, автоматически инжектирующая стандартные лейблы."""

    def __init__(
        self,
        instrument: _M,
        extra_labels: Sequence[str],
    ) -> None:
        self._instrument: _M = instrument
        self._extra_labels = tuple(extra_labels)

    def labels(self, **kwargs: str) -> _M:
        """Возвращает дочерний instrument со всеми лейблами заполненными."""
        values = _label_values_for_dimensions(kwargs)
        # Порядок: сначала стандартные, потом extra в порядке объявления.
        ordered = [values[name] for name in _STANDARD_LABELS]
        ordered += [kwargs[name] for name in self._extra_labels]
        return self._instrument.labels(*ordered)


def _check_no_high_cardinality_labels(labels: Sequence[str]) -> None:
    """Sanity check: запрещаем явно опасные лейблы."""
    forbidden = {
        "request_id",
        "user_id",
        "document_id",
        "trace_id",
        "span_id",
        "session_id",
        "email",
    }
    bad = set(labels) & forbidden
    if bad:
        raise ValueError(
            f"High-cardinality labels rejected: {sorted(bad)}. "
            f"See ADR-0011 §«Контракт метрик»."
        )


def counter(
    name: str,
    documentation: str,
    *,
    labels: Sequence[str] = (),
    registry: CollectorRegistry | None = None,
) -> _LabelledInstrument[Counter]:
    """Создаёт Counter со стандартными + опциональными лейблами."""
    _check_no_high_cardinality_labels(labels)
    all_labels = list(_STANDARD_LABELS) + list(labels)
    c = Counter(
        name,
        documentation,
        all_labels,
        registry=registry or REGISTRY,
    )
    return _LabelledInstrument(c, labels)


def gauge(
    name: str,
    documentation: str,
    *,
    labels: Sequence[str] = (),
    registry: CollectorRegistry | None = None,
) -> _LabelledInstrument[Gauge]:
    """Создаёт Gauge со стандартными + опциональными лейблами."""
    _check_no_high_cardinality_labels(labels)
    all_labels = list(_STANDARD_LABELS) + list(labels)
    g = Gauge(
        name,
        documentation,
        all_labels,
        registry=registry or REGISTRY,
    )
    return _LabelledInstrument(g, labels)


def histogram(
    name: str,
    documentation: str,
    *,
    labels: Sequence[str] = (),
    buckets: Sequence[float] | None = None,
    registry: CollectorRegistry | None = None,
) -> _LabelledInstrument[Histogram]:
    """Создаёт Histogram со стандартными + опциональными лейблами."""
    _check_no_high_cardinality_labels(labels)
    all_labels = list(_STANDARD_LABELS) + list(labels)
    kwargs: dict[str, Any] = {
        "labelnames": all_labels,
        "registry": registry or REGISTRY,
    }
    if buckets:
        kwargs["buckets"] = tuple(buckets)
    h = Histogram(name, documentation, **kwargs)
    return _LabelledInstrument(h, labels)


def render_latest(registry: CollectorRegistry | None = None) -> tuple[bytes, str]:
    """Рендерит метрики в текстовом формате Prometheus.

    Возвращает ``(body, content_type)`` для прямого ответа из HTTP-handler'а
    в случае, когда хочется встроить ``/metrics`` в существующий ASGI/WSGI
    app вместо отдельного сервера.
    """
    body = generate_latest(registry or REGISTRY)
    return body, CONTENT_TYPE_LATEST
