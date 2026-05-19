"""Structured logging setup (structlog).

Per the operating principles: every request line carries ``tenant_id``,
``request_id``, ``model``, ``backend``, ``duration_ms`` and ``status``.
Production emits JSON; dev emits a pretty console renderer.
"""
from __future__ import annotations

import logging
import sys

import structlog

_configured = False


def configure_logging(level: str = "INFO", fmt: str = "json") -> None:
    """Configure structlog and the stdlib root logger.

    Args:
        level: log level name (``DEBUG``/``INFO``/``WARNING``/...).
        fmt: ``"json"`` for production or ``"console"`` for human-readable dev output.

    Idempotent — safe to call once per process (e.g. from the app factory).
    """
    global _configured
    log_level = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=log_level, force=True)

    shared: list[structlog.typing.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True, key="ts"),
    ]
    renderer: structlog.typing.Processor
    if fmt == "console":
        renderer = structlog.dev.ConsoleRenderer()
    else:
        shared.append(structlog.processors.format_exc_info)
        renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=[*shared, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=False,
    )
    _configured = True


def get_logger(name: str = "gateway") -> structlog.stdlib.BoundLogger:
    """Return a bound structlog logger; configures logging on first use."""
    if not _configured:
        configure_logging()
    logger: structlog.stdlib.BoundLogger = structlog.get_logger(name)
    return logger
