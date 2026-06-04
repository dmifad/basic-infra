"""Тесты basic_infra_observability_client.

Покрываем три инварианта SDK:

1. Logging output соответствует JSON-контракту (ADR-0011 §«Контракт логов»).
2. Метрик-фабрики добавляют стандартные лейблы и отвергают
   high-cardinality.
3. contextvars (request_id, tenant_override) корректно проникают в
   логи и метрики.
"""

from __future__ import annotations

import json
import logging
from io import StringIO

import pytest
from prometheus_client import CollectorRegistry

from basic_infra_observability_client import (
    ObservabilitySettings,
    get_logger,
    metrics,
    request_scope,
    setup_logging,
    tenant_scope,
)
from basic_infra_observability_client.metrics import setup_metrics


@pytest.fixture
def settings() -> ObservabilitySettings:
    return ObservabilitySettings(
        service_name="test-service",
        env="dev",
        tenant="test-tenant",
        metrics_enabled=False,
        log_format="json",
    )


@pytest.fixture(autouse=True)
def _reset_metrics_state() -> None:
    """Сбрасываем глобальное состояние metrics SDK между тестами."""
    import basic_infra_observability_client.metrics as m

    m._settings = None
    m._server_started = False
    yield


# --- Logging --------------------------------------------------------


def _capture_log(settings: ObservabilitySettings) -> StringIO:
    """Перенаправляет structlog stdout в StringIO."""
    setup_logging(settings)
    buffer = StringIO()
    handler = logging.StreamHandler(buffer)
    handler.setFormatter(logging.getLogger().handlers[0].formatter)
    logging.getLogger().handlers.clear()
    logging.getLogger().addHandler(handler)
    return buffer


def test_log_output_is_json(settings: ObservabilitySettings) -> None:
    buf = _capture_log(settings)
    log = get_logger("test")
    log.info("hello", extra_field="x")

    line = buf.getvalue().strip()
    assert line, "expected log output"
    payload = json.loads(line)
    assert payload["event"] == "hello"
    assert payload["extra_field"] == "x"


def test_log_contains_standard_labels(
    settings: ObservabilitySettings,
) -> None:
    buf = _capture_log(settings)
    log = get_logger("test")
    log.info("event")

    payload = json.loads(buf.getvalue().strip())
    assert payload["service"] == "test-service"
    assert payload["env"] == "dev"
    assert payload["tenant"] == "test-tenant"
    assert payload["level"] == "info"
    assert "timestamp" in payload


def test_request_scope_injects_request_id(
    settings: ObservabilitySettings,
) -> None:
    buf = _capture_log(settings)
    log = get_logger("test")

    with request_scope("rid-123"):
        log.info("inside")
    log.info("outside")

    lines = [json.loads(line) for line in buf.getvalue().splitlines()]
    inside = next(p for p in lines if p["event"] == "inside")
    outside = next(p for p in lines if p["event"] == "outside")
    assert inside["request_id"] == "rid-123"
    assert "request_id" not in outside


def test_tenant_scope_overrides_default(
    settings: ObservabilitySettings,
) -> None:
    buf = _capture_log(settings)
    log = get_logger("test")

    with tenant_scope("override-tenant"):
        log.info("inside")
    log.info("outside")

    lines = [json.loads(line) for line in buf.getvalue().splitlines()]
    inside = next(p for p in lines if p["event"] == "inside")
    outside = next(p for p in lines if p["event"] == "outside")
    assert inside["tenant"] == "override-tenant"
    assert outside["tenant"] == "test-tenant"


# --- Metrics --------------------------------------------------------


def test_counter_adds_standard_labels(
    settings: ObservabilitySettings,
) -> None:
    registry = CollectorRegistry()
    setup_metrics(settings, start_server=False, registry=registry)

    received = metrics.counter(
        "test_documents_received_total",
        "test",
        labels=["source"],
        registry=registry,
    )
    received.labels(source="portal").inc()

    samples = list(registry.collect())[0].samples
    sample = samples[0]
    assert sample.labels["service"] == "test-service"
    assert sample.labels["env"] == "dev"
    assert sample.labels["tenant"] == "test-tenant"
    assert sample.labels["source"] == "portal"
    assert sample.value == 1.0


def test_tenant_scope_propagates_to_metrics(
    settings: ObservabilitySettings,
) -> None:
    registry = CollectorRegistry()
    setup_metrics(settings, start_server=False, registry=registry)

    c = metrics.counter(
        "test_ops_total", "test", registry=registry,
    )
    with tenant_scope("override-tenant"):
        c.labels().inc()
    c.labels().inc()

    samples = list(registry.collect())[0].samples
    # Counter samples включают _total (значение) и _created (timestamp).
    # Нас интересует только _total.
    by_tenant = {
        s.labels["tenant"]: s.value
        for s in samples
        if s.name.endswith("_total")
    }
    assert by_tenant["override-tenant"] == 1.0
    assert by_tenant["test-tenant"] == 1.0


@pytest.mark.parametrize(
    "bad_label",
    ["request_id", "user_id", "document_id", "trace_id", "session_id"],
)
def test_high_cardinality_labels_rejected(
    settings: ObservabilitySettings, bad_label: str
) -> None:
    registry = CollectorRegistry()
    setup_metrics(settings, start_server=False, registry=registry)

    with pytest.raises(ValueError, match="High-cardinality"):
        metrics.counter(
            "test_bad_total",
            "test",
            labels=[bad_label],
            registry=registry,
        )


def test_histogram_with_buckets(
    settings: ObservabilitySettings,
) -> None:
    registry = CollectorRegistry()
    setup_metrics(settings, start_server=False, registry=registry)

    h = metrics.histogram(
        "test_duration_seconds",
        "test",
        buckets=[0.1, 1, 10],
        registry=registry,
    )
    h.labels().observe(0.5)

    samples = list(registry.collect())[0].samples
    # _bucket samples + _count + _sum + _created
    bucket_samples = [s for s in samples if s.name.endswith("_bucket")]
    assert any(
        s.labels.get("le") == "1.0" and s.value == 1.0
        for s in bucket_samples
    )


def test_metrics_require_setup() -> None:
    """Создание instrument без setup_metrics → RuntimeError при labels()."""
    registry = CollectorRegistry()
    # setup_metrics НЕ вызван
    c = metrics.counter("test_x_total", "test", registry=registry)
    with pytest.raises(RuntimeError, match="setup_metrics"):
        c.labels()


# --- Config ---------------------------------------------------------


def test_settings_require_service_name() -> None:
    import os

    # Чистим env vars на случай "грязного" окружения.
    for key in list(os.environ):
        if key.startswith("BASIC_INFRA_OBSERVABILITY_"):
            del os.environ[key]

    with pytest.raises(Exception):  # pydantic ValidationError
        ObservabilitySettings()


def test_settings_optional_tenant() -> None:
    s = ObservabilitySettings(service_name="prometheus", env="dev")
    assert s.tenant is None
