"""Sinks for the outbox dispatcher (ADR-0019 §4).

The dispatcher delivers each outbox row to a ``Sink``. The first-cut sink is
``LogSink`` (structlog → Loki via the observability SDK); ``RecordingSink`` backs
the delivery tests. No business consumer lives here — the track builds the pipe.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from basic_infra_observability_client import get_logger


@dataclass(frozen=True)
class OutboxEvent:
    """One delivered outbox row (the cross-repo contract shape)."""

    id: int
    event_type: str
    payload: dict[str, Any]
    occurred_at: datetime


class Sink(Protocol):
    async def deliver(self, event: OutboxEvent) -> None: ...


class LogSink:
    """First-cut sink: emit each event via structlog (→ Loki)."""

    def __init__(self) -> None:
        self._log = get_logger("basic_infra_outbox.sink")

    async def deliver(self, event: OutboxEvent) -> None:
        self._log.info(
            "outbox_event_delivered",
            id=event.id,
            event_type=event.event_type,
            occurred_at=event.occurred_at.isoformat(),
            payload=event.payload,
        )


class RecordingSink:
    """In-memory sink for tests — records delivered events in order."""

    def __init__(self) -> None:
        self.events: list[OutboxEvent] = []

    async def deliver(self, event: OutboxEvent) -> None:
        self.events.append(event)
