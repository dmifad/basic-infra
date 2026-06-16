"""Unit tests for basic_infra_observability_client.tracing.

Convention: test_<what>_<when>, no classes. No live collector required — an
InMemorySpanExporter is injected so spans are asserted in-process.
"""

import logging

import pytest

from basic_infra_observability_client.tracing import (
    TraceContextFilter,
    TracingSettings,
    get_tracer,
    install_trace_log_correlation,
    reset_for_tests,
    setup_tracing,
)


@pytest.fixture(autouse=True)
def _reset():
    reset_for_tests()
    yield
    reset_for_tests()


def _memory_exporter():
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )

    return InMemorySpanExporter()


def test_tracing_settings_reads_env_prefix(monkeypatch):
    monkeypatch.setenv("BASIC_INFRA_OBSERVABILITY_TRACING_ENABLED", "true")
    monkeypatch.setenv("BASIC_INFRA_OBSERVABILITY_TRACING_SERVICE_NAME", "telcoss-api")
    monkeypatch.setenv("BASIC_INFRA_OBSERVABILITY_TRACING_ENV", "staging")
    monkeypatch.setenv("BASIC_INFRA_OBSERVABILITY_TRACING_SAMPLE_RATIO", "0.25")

    s = TracingSettings()

    assert s.enabled is True
    assert s.service_name == "telcoss-api"
    assert s.env == "staging"
    assert s.sample_ratio == 0.25


def test_tracing_env_is_not_the_app_env(monkeypatch):
    # The bare ENV must not bleed into the tracing env field.
    monkeypatch.setenv("ENV", "production")
    monkeypatch.delenv("BASIC_INFRA_OBSERVABILITY_TRACING_ENV", raising=False)

    s = TracingSettings()

    assert s.env == "local"


def test_setup_tracing_noop_when_disabled():
    s = TracingSettings(enabled=False, service_name="t")
    exporter = _memory_exporter()

    setup_tracing(settings=s, span_exporter=exporter)

    tracer = get_tracer("t")
    with tracer.start_as_current_span("noop-span"):
        pass

    # No provider was installed, so nothing is recorded.
    assert exporter.get_finished_spans() == ()


def test_setup_tracing_records_span_when_enabled():
    s = TracingSettings(enabled=True, service_name="telcoss-api", env="local")
    exporter = _memory_exporter()

    provider = setup_tracing(settings=s, span_exporter=exporter)

    tracer = provider.get_tracer("telcoss-api")
    with tracer.start_as_current_span("unit-span"):
        pass

    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].name == "unit-span"


def test_setup_tracing_sets_resource_service_name():
    s = TracingSettings(enabled=True, service_name="telcoss-api", env="staging")
    exporter = _memory_exporter()

    provider = setup_tracing(settings=s, span_exporter=exporter)
    with provider.get_tracer("t").start_as_current_span("s"):
        pass

    span = exporter.get_finished_spans()[0]
    assert span.resource.attributes["service.name"] == "telcoss-api"
    assert span.resource.attributes["deployment.environment"] == "staging"


def test_setup_tracing_is_idempotent():
    s = TracingSettings(enabled=True, service_name="t")
    first = setup_tracing(settings=s, span_exporter=_memory_exporter())
    second = setup_tracing(settings=s, span_exporter=_memory_exporter())
    assert first is second


def test_trace_context_filter_injects_ids_inside_span():
    s = TracingSettings(enabled=True, service_name="t")
    provider = setup_tracing(settings=s, span_exporter=_memory_exporter())

    record = logging.LogRecord("x", logging.INFO, __file__, 1, "msg", None, None)
    flt = TraceContextFilter()

    with provider.get_tracer("t").start_as_current_span("span"):
        flt.filter(record)

    assert isinstance(record.trace_id, str) and len(record.trace_id) == 32
    assert isinstance(record.span_id, str) and len(record.span_id) == 16


def test_trace_context_filter_nulls_ids_outside_span():
    record = logging.LogRecord("x", logging.INFO, __file__, 1, "msg", None, None)
    flt = TraceContextFilter()

    flt.filter(record)

    assert record.trace_id is None
    assert record.span_id is None


def test_install_trace_log_correlation_is_idempotent():
    logger = logging.getLogger("test-correlation-logger")
    logger.filters.clear()

    install_trace_log_correlation(logger)
    install_trace_log_correlation(logger)

    assert sum(isinstance(f, TraceContextFilter) for f in logger.filters) == 1


def test_instrument_fastapi_no_op_without_app_crash():
    # Smoke: instrumenting a minimal app must not raise when deps present.
    fastapi = pytest.importorskip("fastapi")
    from basic_infra_observability_client.tracing import instrument_fastapi

    app = fastapi.FastAPI()
    setup_tracing(
        settings=TracingSettings(enabled=True, service_name="t"),
        span_exporter=_memory_exporter(),
    )
    instrument_fastapi(app)  # must not raise
