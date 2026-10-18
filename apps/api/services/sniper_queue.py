from __future__ import annotations

import json
from typing import Any

from sniper.vps_pools import (
    QUEUE_KEYS,
    VpsPool,
    get_vps_pool,
    pools_for_platform,
    queue_keys_for_platform,
)

CONTROL_CHANNEL = "sniper:control"
NODE_HEARTBEAT_PREFIX = "sniper:node:"
STOP_KEY_PREFIX = "sniper:stop:"
PENDING_KEY_PREFIX = "sniper:pending:"
CLAIM_KEY_PREFIX = "sniper:claim:"
NAMES_KEY_PREFIX = "sniper:names:"
OVERFLOW_NODE_ID = "control-api"


def pending_job_key(user_token: str, platform: str) -> str:
    return f"{PENDING_KEY_PREFIX}{user_token}:{platform}"


def claim_job_key(job_id: str) -> str:
    return f"{CLAIM_KEY_PREFIX}{job_id}"


def names_redis_key(user_token: str) -> str:
    return f"{NAMES_KEY_PREFIX}{user_token}"


async def try_claim_job(redis: Any, job_id: str, node_id: str) -> bool:
    """One worker only — prevents double-run when dispatch + BRPOP race."""
    return bool(await redis.set(claim_job_key(job_id), node_id, nx=True, ex=7200))


def node_heartbeat_key(node_id: str) -> str:
    return f"{NODE_HEARTBEAT_PREFIX}{node_id}"


def stop_flag_key(user_token: str, platform: str) -> str:
    return f"{STOP_KEY_PREFIX}{user_token}:{platform}"


async def _pool_busy_idle(redis: Any, pool: VpsPool) -> tuple[int, int]:
    """Return (busy_nodes, idle_nodes) from live heartbeats for a pool."""
    busy = 0
    idle = 0
    cursor: int | bytes = 0
    while True:
        cursor, keys = await redis.scan(
            cursor=cursor, match=f"{NODE_HEARTBEAT_PREFIX}*", count=100
        )
        for key in keys:
            try:
                raw = await redis.get(key)
                if not raw:
                    continue
                data = json.loads(raw)
            except (TypeError, json.JSONDecodeError):
                continue
            if not isinstance(data, dict) or data.get("pool") != pool:
                continue
            if data.get("busy"):
                busy += 1
            else:
                idle += 1
        if cursor == 0 or cursor == b"0":
            break
    return busy, idle


async def pick_least_busy_pool(redis: Any, platform: str) -> VpsPool:
    """Choose the pool with free capacity; fall back to shortest queue."""
    pools = pools_for_platform(platform)
    if len(pools) == 1:
        return pools[0]

    scored: list[tuple[tuple[int, int, int], VpsPool]] = []
    for pool in pools:
        try:
            qlen = int(await redis.llen(QUEUE_KEYS[pool]) or 0)
        except Exception:
            qlen = 0
        try:
            busy, idle = await _pool_busy_idle(redis, pool)
        except Exception:
            busy, idle = 0, 0
        # Prefer idle capacity, then fewer busy+queued, then shorter queue.
        load = busy + qlen
        scored.append(((0 if idle > 0 else 1, load, qlen), pool))

    scored.sort(key=lambda t: t[0])
    return scored[0][1]


async def enqueue_sniper_job(
    redis: Any,
    platform: str,
    payload: dict[str, Any],
    *,
    pool: VpsPool | None = None,
) -> str:
    chosen = pool or await pick_least_busy_pool(redis, platform)
    payload = dict(payload)
    payload["vps_pool"] = chosen
    key = QUEUE_KEYS[chosen]
    await redis.lpush(key, json.dumps(payload))
    return key


async def dequeue_sniper_job(redis: Any, pool: VpsPool, timeout: int = 2) -> dict[str, Any] | None:
    result = await redis.brpop(QUEUE_KEYS[pool], timeout=timeout)
    if not result:
        return None
    _, raw = result
    return json.loads(raw)


async def set_stop_flag(redis: Any, user_token: str, platform: str, *, ttl: int = 3600) -> None:
    """Durable cancel — survives pubsub loss and queued-job races."""
    await redis.set(stop_flag_key(user_token, platform), "1", ex=ttl)


async def clear_stop_flag(redis: Any, user_token: str, platform: str) -> None:
    await redis.delete(stop_flag_key(user_token, platform))


async def is_stop_requested(redis: Any, user_token: str, platform: str) -> bool:
    return bool(await redis.get(stop_flag_key(user_token, platform)))


async def store_names_in_redis(
    redis: Any, user_token: str, names: list[str], *, ttl: int = 86400
) -> str:
    """Share name lists with remote fleets (VPS2) via the central Redis."""
    key = names_redis_key(user_token)
    # Newline payload is smaller/faster than JSON for multi-million lists.
    await redis.set(key, "\n".join(names), ex=ttl)
    return key


async def load_names_from_redis(redis: Any, user_token: str) -> list[str]:
    raw = await redis.get(names_redis_key(user_token))
    if not raw:
        return []
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="ignore")
    return [line.strip() for line in str(raw).splitlines() if line.strip()]


async def purge_queued_jobs(redis: Any, user_token: str, platform: str) -> int:
    """Remove matching jobs still waiting in every pool queue for this platform."""
    removed = 0
    for key in queue_keys_for_platform(platform):
        try:
            items = await redis.lrange(key, 0, -1)
        except Exception:
            continue
        if not items:
            continue
        for raw in items:
            try:
                job = json.loads(raw)
            except (TypeError, json.JSONDecodeError):
                continue
            if not isinstance(job, dict):
                continue
            if job.get("user_token") == user_token and job.get("platform") == platform:
                try:
                    n = await redis.lrem(key, 0, raw)
                    removed += int(n or 0)
                except Exception:
                    continue
    return removed


async def publish_stop(redis: Any, user_token: str, platform: str) -> None:
    await redis.publish(
        CONTROL_CHANNEL,
        json.dumps(
            {
                "action": "stop",
                "user_token": user_token,
                "platform": platform,
            }
        ),
    )


async def prepare_sniper_restart(redis: Any, user_token: str, platform: str) -> dict[str, Any]:
    """Wind down any prior worker/queue state without leaving a durable stop flag.

    request_sniper_stop sets a Redis stop flag that can survive into the next Start
    (especially when pubsub delivers late), causing the new job to abort instantly.
    """
    from services.sniper_dispatch import clear_pending_job
    from services.turbo_sniper_service import clear_live_session, stop_turbo

    purged = await purge_queued_jobs(redis, user_token, platform)
    await clear_pending_job(redis, user_token, platform)
    for _ in range(3):
        await publish_stop(redis, user_token, platform)
    local = stop_turbo(user_token, platform)
    clear_live_session(user_token, platform)
    await clear_stop_flag(redis, user_token, platform)
    return {"purged_queued": purged, "local_engine_stopped": local}


async def request_sniper_stop(redis: Any, user_token: str, platform: str) -> dict[str, Any]:
    """Full stop: durable flag + queue purge + pubsub + best-effort local engine stop."""
    from services.turbo_sniper_service import mark_status_stopped, stop_turbo

    await set_stop_flag(redis, user_token, platform)
    purged = await purge_queued_jobs(redis, user_token, platform)
    # Publish several times — pubsub to remote VPS2 nodes can miss a single message.
    for _ in range(3):
        await publish_stop(redis, user_token, platform)
    local = stop_turbo(user_token, platform)
    await mark_status_stopped(redis, user_token, platform)
    return {
        "purged_queued": purged,
        "local_engine_stopped": local,
        "pool": get_vps_pool(platform),
    }


async def touch_node_heartbeat(
    redis: Any,
    *,
    node_id: str,
    pool: str,
    busy: bool,
    job_id: str | None = None,
    platform: str | None = None,
) -> None:
    payload = {
        "node_id": node_id,
        "pool": pool,
        "busy": busy,
        "job_id": job_id,
        "platform": platform,
    }
    await redis.set(node_heartbeat_key(node_id), json.dumps(payload), ex=30)
