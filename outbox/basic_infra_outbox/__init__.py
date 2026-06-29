"""Generic transactional-outbox dispatcher (ADR-0019, J3.1).

A reusable platform mechanism: it reads unprocessed rows from a consumer's outbox
table, delivers each to a pluggable Sink, and marks them processed. It carries no
consumer specifics — table/channel/dsn/sink are required config supplied by the
consumer.
"""
from __future__ import annotations

from .dispatcher import OutboxDispatcher
from .sinks import LogSink, OutboxEvent, RecordingSink, Sink

__all__ = [
    "OutboxDispatcher",
    "OutboxEvent",
    "Sink",
    "LogSink",
    "RecordingSink",
]
