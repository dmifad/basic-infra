"""Entrypoint — run the generic dispatcher from env config.

The consumer (telcoss) supplies the contract values:
  OUTBOX_DSN      — connection string as the reader role (outbox_reader@tenant-db)
  OUTBOX_TABLE    — schema-qualified table (default inventory.outbox)
  OUTBOX_CHANNEL  — NOTIFY channel (default telcoss_outbox)
"""
from __future__ import annotations

import asyncio
import os

from basic_infra_observability_client import ObservabilitySettings, setup_logging

from .dispatcher import OutboxDispatcher
from .sinks import LogSink


def main() -> None:
    setup_logging(ObservabilitySettings(service_name="outbox-dispatcher"))
    dispatcher = OutboxDispatcher(
        dsn=os.environ["OUTBOX_DSN"],
        table=os.environ.get("OUTBOX_TABLE", "inventory.outbox"),
        channel=os.environ.get("OUTBOX_CHANNEL", "telcoss_outbox"),
        sink=LogSink(),
        poll_interval=float(os.environ.get("OUTBOX_POLL_SECONDS", "30")),
    )
    asyncio.run(dispatcher.run())


if __name__ == "__main__":
    main()
