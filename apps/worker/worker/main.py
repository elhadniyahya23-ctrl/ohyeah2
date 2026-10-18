from __future__ import annotations

import asyncio
import json
import logging
import time

import redis.asyncio as redis

from worker.config import settings
from worker.engine.runner import RunStats, SniperEngine

logger = logging.getLogger(__name__)

JOBS_KEY = "sniper:jobs"
CONTROL_CHANNEL = "sniper:control"
HEARTBEAT_KEY = "sniper:worker:heartbeat"


class JobRunner:
    def __init__(self, r: redis.Redis):
        self.redis = r
        self._stop = asyncio.Event()
        self._pause = asyncio.Event()
        self._pause.set()
        self._current_platform: str | None = None
        self._engine = SniperEngine(self.redis, stop_event=self._stop, pause_event=self._pause)

    async def listen_control(self):
        pubsub = self.redis.pubsub()
        await pubsub.subscribe(CONTROL_CHANNEL)
        async for message in pubsub.listen():
            if message["type"] != "message":
                continue
            data = json.loads(message["data"])
            action = data.get("action")
            target = data.get("platform")

            if target and self._current_platform and target != self._current_platform:
                continue

            if action == "stop":
                self._stop.set()
            elif action == "pause":
                self._pause.clear()
            elif action == "resume":
                self._pause.set()

    async def heartbeat_loop(self):
        while True:
            try:
                await self.redis.set(HEARTBEAT_KEY, str(time.time()), ex=30)
            except Exception:
                logger.exception("Worker heartbeat failed")
            await asyncio.sleep(5)

    async def run_job(self, job: dict):
        platform = job["platform"]
        total = int(job.get("total_names") or len(job.get("names") or []))

        if platform not in settings.platform_list:
            await self._engine.update_status(platform, RunStats(errors=1), total, "idle")
            return

        self._stop.clear()
        self._pause.set()
        self._current_platform = platform
        try:
            await self._engine.update_status(platform, RunStats(), total, "running")
            await self._engine.run(job)
        except Exception:
            logger.exception("Worker job failed for %s", platform)
            await self._engine.update_status(platform, RunStats(errors=1), total, "interrupted")
        finally:
            self._current_platform = None
            self._stop.clear()
            self._pause.set()

    async def poll_jobs(self):
        while True:
            try:
                result = await self.redis.brpop(JOBS_KEY, timeout=2)
                if not result:
                    continue
                _, payload = result
                job = json.loads(payload)
                await self.run_job(job)
            except Exception:
                logger.exception("Worker job failed — continuing to poll")
                await asyncio.sleep(1)


async def main():
    r = redis.from_url(settings.redis_url, decode_responses=True)
    runner = JobRunner(r)
    await asyncio.gather(runner.listen_control(), runner.poll_jobs(), runner.heartbeat_loop())


if __name__ == "__main__":
    asyncio.run(main())
