"""Metrics — stubs only.

Real Prometheus instrumentation arrives in Week 6 with the observability layer
(ADR-0001 § "Out of scope for Week 4"). These no-ops give call sites a stable
seam to wire against now.
"""
from __future__ import annotations


def record_request(
    *,
    tenant_id: str | None,
    endpoint: str,
    status: int,
    duration_ms: float,
) -> None:
    """Record one served request.

    No-op until Week 6, when this emits a Prometheus counter + latency histogram.
    """
    # TODO(week6): emit prometheus_client Counter / Histogram.
    return None
