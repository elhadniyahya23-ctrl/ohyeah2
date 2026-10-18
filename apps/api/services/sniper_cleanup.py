"""Stop orphaned / unauthorized live sniper sessions (proxy burn protection)."""

from __future__ import annotations

import json
import logging
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import User
from services.plans import is_admin, user_has_active_plan
from services.sniper_dispatch import is_stuck_starting, maybe_start_overflow_job
from services.sniper_queue import request_sniper_stop

logger = logging.getLogger(__name__)

CleanupMode = Literal["orphans", "unauthorized", "all"]


async def scan_status_keys(redis: Any) -> list[tuple[str, str, dict]]:
    """Return (token, platform, status_dict) for every sniper:status:* key."""
    cursor = 0
    keys: list[str] = []
    while True:
        cursor, batch = await redis.scan(cursor=cursor, match="sniper:status:*", count=200)
        keys.extend(batch)
        if cursor == 0:
            break

    parsed: list[tuple[str, str, dict]] = []
    for key in keys:
        parts = key.split(":", 3)
        if len(parts) < 4:
            continue
        token = parts[2]
        platform = parts[3]
        raw = await redis.get(key)
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        parsed.append((token, platform, data))
    return parsed


def _is_active(data: dict) -> bool:
    return (data.get("state") or "idle").lower() in ("running", "queued")


def _is_stuck_queued(data: dict) -> bool:
    return is_stuck_starting(data)


async def recover_stuck_queued_sessions(redis: Any) -> int:
    """Kick stuck starts — overflow on control API if fleet workers did not pick up."""
    sessions = await scan_status_keys(redis)
    recovered = 0
    for token, platform, data in sessions:
        if not is_stuck_starting(data):
            continue
        # Discord waits in Redis for a free sniper-node slot — that is expected under
        # the concurrency cap, not a stuck start. Never kill or overflow those.
        if (platform or "").lower() == "discord":
            continue
        try:
            if await maybe_start_overflow_job(redis, token, platform, data):
                recovered += 1
                logger.warning(
                    "Overflow-started stuck sniper token=%s… platform=%s",
                    token[:8],
                    platform,
                )
                continue
            from services.turbo_sniper_service import mark_status_stopped

            await request_sniper_stop(redis, token, platform)
            await mark_status_stopped(redis, token, platform)
            recovered += 1
            logger.warning(
                "Cleared stuck sniper token=%s… platform=%s",
                token[:8],
                platform,
            )
        except Exception:
            logger.exception("Failed to recover stuck start %s/%s", token[:8], platform)
    return recovered


async def cleanup_live_snipers(
    redis: Any,
    db: AsyncSession,
    *,
    mode: CleanupMode = "unauthorized",
) -> dict[str, Any]:
    """Force-stop live sessions that should not be running.

    Modes:
      - orphans: token has no matching User.token in DB
      - unauthorized: orphans + users without an active plan (expired trial, etc.)
      - all: every running/queued session
    """
    sessions = await scan_status_keys(redis)
    active = [(t, p, d) for t, p, d in sessions if _is_active(d)]
    if not active:
        return {"stopped": 0, "mode": mode, "details": []}

    tokens = {t for t, _, _ in active}
    token_to_user: dict[str, User] = {}
    if tokens:
        result = await db.execute(select(User).where(User.token.in_(list(tokens))))
        for u in result.scalars().all():
            if u.token:
                token_to_user[u.token] = u

    details: list[dict[str, Any]] = []
    for token, platform, data in active:
        owner = token_to_user.get(token)
        orphan = owner is None
        unauthorized = orphan or (
            owner is not None and not is_admin(owner) and not user_has_active_plan(owner)
        )

        should_stop = False
        reason = ""
        if mode == "all":
            should_stop = True
            reason = "kill_all"
        elif mode == "orphans" and orphan:
            should_stop = True
            reason = "orphan"
        elif mode == "unauthorized" and unauthorized:
            should_stop = True
            reason = "orphan" if orphan else "no_active_plan"

        if not should_stop:
            continue

        try:
            result = await request_sniper_stop(redis, token, platform)
        except Exception:
            logger.exception("Failed to stop sniper %s/%s", token[:8], platform)
            details.append(
                {
                    "user_token_prefix": token[:12],
                    "platform": platform,
                    "reason": reason,
                    "username": owner.username if owner else None,
                    "ok": False,
                }
            )
            continue

        details.append(
            {
                "user_token_prefix": token[:12],
                "platform": platform,
                "reason": reason,
                "username": owner.username if owner else None,
                "rank": owner.rank if owner else None,
                "ok": True,
                **result,
            }
        )
        logger.warning(
            "Cleanup stopped sniper token=%s… platform=%s reason=%s user=%s",
            token[:8],
            platform,
            reason,
            owner.username if owner else "unknown",
        )

    return {"stopped": len([d for d in details if d.get("ok")]), "mode": mode, "details": details}
