"""Kill every running/queued sniper and zero all Redis session stats."""

from __future__ import annotations

import asyncio
import json
import sys

import redis.asyncio as redis

from config import settings
from services.sniper_queue import CONTROL_CHANNEL, request_sniper_stop


async def main() -> int:
    r = redis.from_url(settings.redis_url, decode_responses=True)
    stopped = 0
    zeroed = 0
    try:
        cursor = 0
        keys: list[str] = []
        while True:
            cursor, batch = await r.scan(cursor=cursor, match="sniper:status:*", count=200)
            keys.extend(batch)
            if cursor == 0:
                break

        for key in keys:
            raw = await r.get(key)
            if not raw:
                continue
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if not isinstance(data, dict):
                continue

            parts = key.split(":", 3)
            if len(parts) < 4:
                continue
            token, platform = parts[2], parts[3]
            state = (data.get("state") or "idle").lower()
            if state in ("running", "queued"):
                await request_sniper_stop(r, token, platform)
                stopped += 1

            platform_val = data.get("platform") or platform
            fresh = {
                "platform": platform_val,
                "state": "idle",
                "progress_pct": 0,
                "checks_done": 0,
                "total_names": 0,
                "checks_per_sec": 0,
                "valid_checks_per_sec": 0,
                "recovery_mode": False,
                "available": 0,
                "occupied": 0,
                "errors": 0,
                "rate_limits": 0,
                "proxy_misses": 0,
                "elapsed_seconds": 0,
                "current_target": None,
                "captures": [],
                "trial_remaining_seconds": data.get("trial_remaining_seconds"),
                "trial_exhausted": data.get("trial_exhausted", False),
                "redirect_to_payment": data.get("redirect_to_payment", False),
                "infinite": False,
            }
            await r.set(key, json.dumps(fresh))
            zeroed += 1

        # Flush queues so nothing re-starts stale jobs.
        for q in ("sniper:queue:vps1", "sniper:queue:vps2", "sniper:queue:vps3"):
            await r.delete(q)

        await r.publish(CONTROL_CHANNEL, json.dumps({"action": "stop_all"}))
        print(json.dumps({"stopped": stopped, "zeroed": zeroed}, indent=2))
    finally:
        await r.aclose()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
