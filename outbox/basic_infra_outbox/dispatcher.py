"""Generic outbox dispatcher engine (ADR-0019 §6).

The outbox table is the source of truth. The dispatcher delivers unprocessed rows
ordered by ``id``, then marks them processed. ``LISTEN`` on the channel is an
accelerator; a startup self-scan plus a periodic self-scan are the safety net, so
a NOTIFY lost across a restart or a dropped listen-connection never loses a row.
At-least-once (deliver before mark → a crash between them redelivers); ordering is
best-effort by ``id``. One tenant, one instance, first cut.
"""
from __future__ import annotations

import asyncio
import json

import asyncpg
from basic_infra_observability_client import get_logger

from .sinks import OutboxEvent, Sink

log = get_logger("basic_infra_outbox.dispatcher")


class OutboxDispatcher:
    def __init__(
        self,
        *,
        dsn: str,
        table: str,
        channel: str,
        sink: Sink,
        poll_interval: float = 30.0,
    ) -> None:
        self._dsn = dsn
        self._table = table  # schema-qualified, e.g. "inventory.outbox"
        self._channel = channel
        self._sink = sink
        self._poll = poll_interval

    async def deliver_backlog(self, conn: asyncpg.Connection) -> int:
        """Deliver every currently-unprocessed row in id order; return the count.

        Tolerates the table not existing yet (logs + returns 0, no crash-loop).
        Delivers each row to the sink BEFORE marking it processed, so a crash in
        between redelivers — at-least-once.
        """
        try:
            rows = await conn.fetch(
                f"SELECT id, event_type, payload, occurred_at FROM {self._table} "
                "WHERE processed_at IS NULL ORDER BY id"
            )
        except asyncpg.UndefinedTableError:
            log.warning("outbox_table_absent", table=self._table)
            return 0
        delivered = 0
        for row in rows:
            payload = row["payload"]
            event = OutboxEvent(
                id=row["id"],
                event_type=row["event_type"],
                payload=json.loads(payload) if isinstance(payload, str) else payload,
                occurred_at=row["occurred_at"],
            )
            await self._sink.deliver(event)
            await conn.execute(
                f"UPDATE {self._table} SET processed_at = now() WHERE id = $1",
                row["id"],
            )
            delivered += 1
        if delivered:
            log.info("outbox_backlog_delivered", table=self._table, count=delivered)
        return delivered

    async def run(self, *, stop: asyncio.Event | None = None) -> None:
        """Long-running loop: startup self-scan → LISTEN → on doorbell or poll
        timeout, self-scan again. Runs until ``stop`` is set (None = forever)."""
        conn = await asyncpg.connect(self._dsn)
        try:
            await self.deliver_backlog(conn)  # drain backlog before listening
            doorbell = asyncio.Event()
            await conn.add_listener(self._channel, lambda *_: doorbell.set())
            log.info("outbox_dispatcher_listening", channel=self._channel)
            while stop is None or not stop.is_set():
                try:
                    await asyncio.wait_for(doorbell.wait(), timeout=self._poll)
                except TimeoutError:
                    pass  # periodic safety-net self-scan
                doorbell.clear()
                await self.deliver_backlog(conn)
        finally:
            await conn.close()
