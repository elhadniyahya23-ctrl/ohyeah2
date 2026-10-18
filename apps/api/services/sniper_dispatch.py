"""Immediate sniper job dispatch — no user-visible queue / priority."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

from services.sniper_queue import (
    CONTROL_CHANNEL,
    OVERFLOW_NODE_ID,
    claim_job_key,
    pending_job_key,
    purge_queued_jobs,
    try_claim_job,
)

logger = logging.getLogger(__name__)

# Only treat as stuck when there is truly no worker activity (not just late proxies).
STUCK_START_SECONDS = 20


async def store_pending_job(redis: Any, user_token: str, platform: str, payload: dict) -> None:
    await redis.set(pending_job_key(user_token, platform), json.dumps(payload), ex=3600)


async def clear_pending_job(redis: Any, user_token: str, platform: str) -> None:
    await redis.delete(pending_job_key(user_token, platform))


async def publish_dispatch(redis: Any, payload: dict) -> None:
    """Wake idle sniper-node workers immediately (no BRPOP wait)."""
    await redis.publish(
        CONTROL_CHANNEL,
        json.dumps({"action": "dispatch", "job": payload}),
    )


def is_stuck_starting(data: dict) -> bool:
    """Running/queued with zero activity for too long — worker never started.

    Late proxies / rate-limits still count as activity so social snipers are not
    killed mid-run just because checks_done is still 0.
    """
    state = (data.get("state") or "idle").lower()
    if state not in ("queued", "running"):
        return False
    activity = (
        int(data.get("checks_done") or 0)
        + int(data.get("proxy_misses") or 0)
        + int(data.get("rate_limits") or 0)
        + int(data.get("errors") or 0)
        + int(data.get("available") or 0)
        + int(data.get("occupied") or 0)
    )
    if activity > 0:
        return False
    # Prefer running_started_at so queue wait does not burn the stuck timer.
    started_at = float(data.get("running_started_at") or data.get("started_at") or 0)
    if not started_at:
        return False
    return int(time.time() - started_at) >= STUCK_START_SECONDS


async def maybe_start_overflow_job(redis: Any, user_token: str, platform: str, data: dict) -> bool:
    """Last resort: run the job on the control API if fleet workers did not pick it up."""
    if not is_stuck_starting(data):
        return False

    # Discord throughput is capped by sniper-node replicas. Overflow onto the control
    # API would add a 3rd+ concurrent job and collapse everyone's CPS under 5.
    if (platform or "").lower() == "discord":
        return False

    raw = await redis.get(pending_job_key(user_token, platform))
    if not raw:
        return False

    try:
        job = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return False
    if not isinstance(job, dict) or not job.get("job_id"):
        return False

    if not await try_claim_job(redis, str(job["job_id"]), OVERFLOW_NODE_ID):
        return False

    await purge_queued_jobs(redis, user_token, platform)
    await clear_pending_job(redis, user_token, platform)

    from services.turbo_sniper_service import run_turbo_job

    logger.warning(
        "Overflow dispatch job %s for %s/%s on control API",
        job.get("job_id"),
        user_token[:8],
        platform,
    )
    asyncio.create_task(
        run_turbo_job(
            redis=redis,
            job_id=job["job_id"],
            user_id=int(job["user_id"]),
            user_token=user_token,
            platform=platform,
            targets=job.get("targets") or None,
            proxy_lines=job["proxy_lines"],
            webhook_url=job.get("webhook_url"),
            workers=int(job.get("workers") or 160),
            infinite=bool(job.get("infinite")),
            load_targets_from_file=bool(job.get("load_targets_from_file")),
            load_targets_from_redis=bool(job.get("load_targets_from_redis")),
            targets_count=int(job["targets_count"]) if job.get("targets_count") else None,
            node_id=OVERFLOW_NODE_ID,
            rotate_sessions=bool(job.get("rotate_sessions")),
        )
    )
    return True
