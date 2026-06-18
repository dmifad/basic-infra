"""Background backend health checker (ADR-0005).

Probes every registered adapter on a fixed interval. An adapter is marked
unhealthy only after ``unhealthy_threshold`` consecutive failed probes; the
router then fails fast on it instead of waiting for a timeout. ``/ready``
reflects the aggregate state.
"""
from __future__ import annotations

import asyncio
import contextlib

from ..observability.logging import get_logger
from .registry import Registry

_log = get_logger("health")


class HealthChecker:
    """Periodically probes backend health and updates adapter state."""

    def __init__(
        self,
        registry: Registry,
        *,
        interval_seconds: int,
        unhealthy_threshold: int,
    ) -> None:
        self._registry = registry
        self._interval = interval_seconds
        self._threshold = unhealthy_threshold
        self._task: asyncio.Task[None] | None = None

    async def check_once(self) -> None:
        """Probe every adapter once and fold the result into its health state."""
        for adapter in self._registry.adapters:
            try:
                ok = await adapter.health()
            except Exception as exc:  # a probe must never crash the loop
                _log.warning("health_probe_error", backend=adapter.name, error=str(exc))
                ok = False
            recovered = adapter.record_health(ok, unhealthy_threshold=self._threshold)
            if recovered:
                _log.info(
                    "backend_client_reconnect",
                    backend=adapter.name,
                    reason="health_recovery_edge",
                )
                await adapter.reconnect()
            if not ok:
                _log.warning(
                    "backend_probe_failed",
                    backend=adapter.name,
                    consecutive_failures=adapter.consecutive_failures,
                    healthy=adapter.is_healthy,
                )

    async def _loop(self) -> None:
        while True:
            await asyncio.sleep(self._interval)
            await self.check_once()

    async def start(self) -> None:
        """Spawn the background probe loop (idempotent)."""
        if self._task is None:
            self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        """Cancel the background probe loop and wait for it to unwind."""
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
