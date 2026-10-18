from __future__ import annotations

import asyncio
import json
import logging
import os
import socket
import uuid
from typing import Any

from config import settings
from services.sniper_queue import (
    CONTROL_CHANNEL,
    dequeue_sniper_job,
    is_stop_requested,
    set_stop_flag,
    touch_node_heartbeat,
    try_claim_job,
)
from services.turbo_sniper_service import mark_status_stopped, run_turbo_job, stop_turbo
from sniper.vps_pools import VpsPool, pool_supports_platform

logger = logging.getLogger(__name__)


def _node_id() -> str:
    explicit = (settings.sniper_node_id or "").strip()
    if explicit:
        return explicit
    host = socket.gethostname()
    return f"{host}-{os.getpid()}-{uuid.uuid4().hex[:8]}"


class SniperNodeRunner:
    """Dedicated API process: one active sniper job at a time, turbo in-process."""

    def __init__(self, redis: Any, pool: VpsPool) -> None:
        self.redis = redis
        self.pool: VpsPool = pool
        self.node_id = _node_id()
        self._stop = asyncio.Event()
        self._current_job: dict | None = None
        self._tasks: list[asyncio.Task] = []

    async def start(self) -> None:
        logger.info(
            "Sniper node %s online (pool=%s, max_jobs=%s)",
            self.node_id,
            self.pool,
            settings.sniper_node_max_jobs,
        )
        self._tasks = [
            asyncio.create_task(self._control_listener(), name="sniper-control"),
            asyncio.create_task(self._stop_poller(), name="sniper-stop-poller"),
            asyncio.create_task(self._heartbeat_loop(), name="sniper-heartbeat"),
            asyncio.create_task(self._job_loop(), name="sniper-jobs"),
        ]

    async def shutdown(self) -> None:
        self._stop.set()
        if self._current_job:
            stop_turbo(self._current_job["user_token"], self._current_job["platform"])
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)

    async def _heartbeat_loop(self) -> None:
        while not self._stop.is_set():
            try:
                job = self._current_job
                await touch_node_heartbeat(
                    self.redis,
                    node_id=self.node_id,
                    pool=self.pool,
                    busy=job is not None,
                    job_id=job.get("job_id") if job else None,
                    platform=job.get("platform") if job else None,
                )
            except Exception:
                logger.exception("Node heartbeat failed")
            await asyncio.sleep(5)

    async def _control_listener(self) -> None:
        """Pubsub stop channel — retried forever (remote VPS2→VPS1 pubsub can drop)."""
        while not self._stop.is_set():
            pubsub = self.redis.pubsub()
            try:
                await pubsub.subscribe(CONTROL_CHANNEL)
                async for message in pubsub.listen():
                    if self._stop.is_set():
                        break
                    if message.get("type") != "message":
                        continue
                    try:
                        data = json.loads(message["data"])
                    except (json.JSONDecodeError, TypeError):
                        continue
                    action = data.get("action")
                    if action == "stop":
                        await self._handle_stop_message(data)
                    elif action == "dispatch":
                        await self._handle_dispatch_message(data)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Control listener failed — retrying in 2s")
                await asyncio.sleep(2)
            finally:
                try:
                    await pubsub.unsubscribe(CONTROL_CHANNEL)
                    await pubsub.aclose()
                except Exception:
                    pass

    async def _stop_poller(self) -> None:
        """Poll Redis stop flags every 250ms — works even when pubsub is unreliable."""
        while not self._stop.is_set():
            job = self._current_job
            if job:
                user_token = job.get("user_token", "")
                platform = job.get("platform", "")
                try:
                    if user_token and platform and await is_stop_requested(
                        self.redis, user_token, platform
                    ):
                        stop_turbo(user_token, platform)
                        try:
                            await mark_status_stopped(self.redis, user_token, platform)
                        except Exception:
                            pass
                except Exception:
                    logger.exception("Stop poller check failed")
            await asyncio.sleep(0.25)

    async def _handle_stop_message(self, data: dict) -> None:
        if data.get("action") != "stop":
            return
        user_token = data.get("user_token")
        platform = data.get("platform")
        if not user_token or not platform:
            return
        job = self._current_job
        if not job:
            return
        if user_token != job.get("user_token") or platform != job.get("platform"):
            return
        try:
            await set_stop_flag(self.redis, user_token, platform)
        except Exception:
            pass
        stop_turbo(job["user_token"], job["platform"])
        try:
            await mark_status_stopped(self.redis, job["user_token"], job["platform"])
        except Exception:
            pass

    async def _handle_dispatch_message(self, data: dict) -> None:
        if self._current_job is not None:
            return
        job = data.get("job")
        if not isinstance(job, dict):
            return
        platform = job.get("platform", "")
        if not platform or not pool_supports_platform(self.pool, platform):
            return
        user_token = job.get("user_token", "")
        if not user_token:
            return
        if await is_stop_requested(self.redis, user_token, platform):
            return
        job_id = str(job.get("job_id") or "")
        if job_id and not await try_claim_job(self.redis, job_id, self.node_id):
            return
        self._current_job = job
        try:
            await self._run_job(job)
        finally:
            self._current_job = None

    async def _job_loop(self) -> None:
        while not self._stop.is_set():
            if self._current_job is not None:
                await asyncio.sleep(0.05)
                continue
            try:
                job = await dequeue_sniper_job(self.redis, self.pool, timeout=2)
            except Exception:
                logger.exception("Queue dequeue failed")
                await asyncio.sleep(1)
                continue
            if not job:
                continue
            job_id = str(job.get("job_id") or "")
            if job_id and not await try_claim_job(self.redis, job_id, self.node_id):
                logger.info("Skipping job %s — already claimed", job_id)
                continue
            # Skip jobs that were cancelled while still queued.
            try:
                if await is_stop_requested(
                    self.redis, job.get("user_token", ""), job.get("platform", "")
                ):
                    logger.info(
                        "Skipping cancelled job %s (%s)",
                        job.get("job_id"),
                        job.get("platform"),
                    )
                    continue
            except Exception:
                logger.exception("Stop-flag check failed")
            self._current_job = job
            try:
                await self._run_job(job)
            finally:
                self._current_job = None

    async def _run_job(self, job: dict) -> None:
        platform = job["platform"]
        user_token = job["user_token"]
        infinite = bool(job.get("infinite"))

        if await is_stop_requested(self.redis, user_token, platform):
            await mark_status_stopped(self.redis, user_token, platform)
            return

        await run_turbo_job(
            job_id=job["job_id"],
            user_id=int(job["user_id"]),
            user_token=user_token,
            platform=platform,
            targets=job.get("targets") or None,
            proxy_lines=job["proxy_lines"],
            webhook_url=job.get("webhook_url"),
            workers=int(job.get("workers") or settings.turbo_workers),
            redis=self.redis,
            infinite=infinite,
            load_targets_from_file=bool(job.get("load_targets_from_file")),
            load_targets_from_redis=bool(job.get("load_targets_from_redis")),
            targets_count=int(job["targets_count"]) if job.get("targets_count") else None,
            node_id=self.node_id,
            rotate_sessions=bool(job.get("rotate_sessions")),
        )
