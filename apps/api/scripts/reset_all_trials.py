"""Reset every Free Trial account to a fresh 5-minute balance.

Usage (on VPS):
  docker compose -f infra/docker/docker-compose.control.yml exec -T api \\
    python -m scripts.reset_all_trials
"""

from __future__ import annotations

import asyncio
import json

import redis.asyncio as aioredis
from sqlalchemy import or_, select

from config import settings
from database import SessionLocal, User
from services.plans import is_admin_username
from services.sniper_queue import request_sniper_stop
from services.turbo_sniper_service import mark_status_stopped


async def reset_all_trials(*, clear_sessions: bool = True) -> dict[str, int]:
    redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    reset_users = 0
    stopped_sessions = 0
    cleared_status = 0

    try:
        async with SessionLocal() as db:
            result = await db.execute(
                select(User).where(
                    or_(
                        User.rank.ilike("%free trial%"),
                        User.rank.ilike("%trial%"),
                    )
                )
            )
            users = list(result.scalars().all())
            for user in users:
                if is_admin_username(user.username):
                    continue
                rank = (user.rank or "").lower()
                if "trial" not in rank:
                    continue
                # Skip active paid plans that no longer use trial rank naming.
                if "trial" not in rank and user.plan_expires_at:
                    continue

                user.rank = "Free Trial"
                user.trial_used_seconds = 0
                user.plan_expires_at = None
                reset_users += 1

            await db.commit()

        if clear_sessions:
            cursor = 0
            keys: list[str] = []
            while True:
                cursor, batch = await redis.scan(
                    cursor=cursor, match="sniper:status:*", count=200
                )
                keys.extend(batch)
                if cursor == 0:
                    break

            trial_tokens = {u.token for u in users if u.token and not is_admin_username(u.username)}

            for key in keys:
                parts = key.split(":", 3)
                if len(parts) < 4:
                    continue
                token, platform = parts[2], parts[3]
                if token not in trial_tokens:
                    continue
                raw = await redis.get(key)
                if not raw:
                    continue
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                state = (data.get("state") or "idle").lower()
                if state in ("running", "queued"):
                    await request_sniper_stop(redis, token, platform)
                    stopped_sessions += 1
                await mark_status_stopped(redis, token, platform)
                cleared_status += 1

            for user in users:
                if is_admin_username(user.username) or not user.id:
                    continue
                await redis.delete(f"sniper:trial:lock:{user.id}")

    finally:
        await redis.aclose()

    return {
        "users_reset": reset_users,
        "sessions_stopped": stopped_sessions,
        "status_cleared": cleared_status,
    }


async def main() -> int:
    stats = await reset_all_trials()
    print(json.dumps(stats, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
