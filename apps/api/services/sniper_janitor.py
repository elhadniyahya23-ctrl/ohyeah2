"""Periodic cleanup of orphan / unauthorized live snipers on the control plane."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from database import SessionLocal
from services.sniper_cleanup import cleanup_live_snipers, recover_stuck_queued_sessions

logger = logging.getLogger(__name__)

# How often the control plane sweeps Redis for proxy-burning orphans.
JANITOR_INTERVAL_SECONDS = 30


class SniperJanitor:
    def __init__(self, redis: Any, *, interval: float = JANITOR_INTERVAL_SECONDS) -> None:
        self.redis = redis
        self.interval = interval
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()

    async def start(self) -> None:
        if self._task is not None:
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._loop(), name="sniper-janitor")

    async def shutdown(self) -> None:
        self._stop.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _loop(self) -> None:
        # Small delay so Redis/DB are ready after boot.
        await asyncio.sleep(5)
        while not self._stop.is_set():
            try:
                async with SessionLocal() as db:
                    result = await cleanup_live_snipers(
                        self.redis, db, mode="unauthorized"
                    )
                stopped = int(result.get("stopped") or 0)
                if stopped:
                    logger.warning(
                        "Sniper janitor stopped %s unauthorized session(s)", stopped
                    )
                recovered = await recover_stuck_queued_sessions(self.redis)
                if recovered:
                    logger.warning(
                        "Sniper janitor cleared %s stuck queued session(s)", recovered
                    )
            except Exception:
                logger.exception("Sniper janitor sweep failed")
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.interval)
            except asyncio.TimeoutError:
                pass
