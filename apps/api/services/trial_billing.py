"""Helpers for Free Trial wall-clock billing (DB-backed, abuse-resistant)."""

from __future__ import annotations

import time
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from database import User
from services.plans import (
    TRIAL_LIMIT_SECONDS,
    add_trial_seconds,
    is_trial_user,
    trial_remaining_seconds,
)


def _running_anchor(data: dict[str, Any]) -> float:
    """When the worker is actually checking names — excludes time stuck in queue."""
    raw = data.get("running_started_at") or data.get("started_at") or 0
    try:
        return float(raw)
    except (TypeError, ValueError):
        return 0.0


def _engine_activity(data: dict[str, Any]) -> int:
    """Any proof the sniper engine has started doing work."""
    return (
        int(data.get("checks_done") or 0)
        + int(data.get("rate_limits") or 0)
        + int(data.get("errors") or 0)
        + int(data.get("proxy_misses") or 0)
        + int(data.get("available") or 0)
        + int(data.get("occupied") or 0)
    )


def session_elapsed(data: dict[str, Any]) -> int:
    """Wall-clock seconds to bill for the current sniper session.

    Queued time does NOT count — users were losing trial minutes while stuck in
    queue (deploy outages, oversized job payloads) with zero checks running.
    """
    stored = int(data.get("elapsed_seconds") or 0)
    state = (data.get("state") or "idle").lower()
    if state == "queued":
        return stored
    if state == "running":
        # Prefer the worker-start anchor; fall back to UI started_at so elapsed
        # (and Free Trial) still advance when the fleet is slow to claim.
        anchor_raw = data.get("running_started_at")
        if anchor_raw is None:
            anchor_raw = data.get("started_at")
        try:
            anchor = float(anchor_raw or 0)
        except (TypeError, ValueError):
            anchor = 0.0
        if anchor:
            return max(stored, int(time.time() - anchor))
    return stored


def billable_trial_seconds(data: dict[str, Any]) -> int:
    """Seconds that should debit the user's trial balance.

    Free Trial burns while the UI shows running. Queue wait does not burn.
    A short grace avoids charging the fleet handoff (~few seconds).
    """
    state = (data.get("state") or "idle").lower()
    if state == "queued":
        return 0
    if state != "running":
        return int(data.get("elapsed_seconds") or 0)
    elapsed = session_elapsed(data)
    # Grace for Redis/fleet handoff before the first check lands.
    if _engine_activity(data) <= 0 and elapsed < 8:
        return 0
    return elapsed


def pending_trial_seconds(data: dict[str, Any]) -> int:
    """Wall-clock trial seconds not yet written to users.trial_used_seconds."""
    already = int(data.get("trial_billed_seconds") or 0)
    return max(0, billable_trial_seconds(data) - already)


def trial_remaining_with_pending(user: User, data: dict[str, Any]) -> int:
    """UI-facing remaining seconds including unbilled wall-clock (no Neon round-trip)."""
    return max(0, trial_remaining_seconds(user) - pending_trial_seconds(data))


async def bill_trial_progress(
    db: AsyncSession,
    user: User,
    data: dict[str, Any],
    *,
    force_complete: bool = False,
) -> tuple[User, int]:
    """Persist unbilled session seconds into users.trial_used_seconds.

    Returns (user, seconds_just_billed). Safe to call on every status poll —
    only the delta since last bill is written. F5 cannot reset DB usage.
    """
    if not is_trial_user(user):
        return user, 0

    state = (data.get("state") or "idle").lower()
    if state == "queued":
        return user, 0

    elapsed = billable_trial_seconds(data)
    data["elapsed_seconds"] = session_elapsed(data)
    already = int(data.get("trial_billed_seconds") or 0)
    unbilled = max(0, elapsed - already)
    if unbilled <= 0:
        if force_complete:
            data["trial_billed"] = True
        return user, 0

    remaining = trial_remaining_seconds(user)
    # During live polls, only flush to DB every ~3s (or when trial is about to end).
    # Stop / force_complete always flushes the full delta.
    if not force_complete and unbilled < 3 and remaining > unbilled:
        return user, 0

    to_add = min(unbilled, remaining) if remaining > 0 else 0
    if to_add <= 0:
        data["trial_billed"] = True
        return user, 0

    user = await add_trial_seconds(db, user, to_add)
    data["trial_billed_seconds"] = already + to_add
    if force_complete or trial_remaining_seconds(user) <= 0 or already + to_add >= elapsed:
        data["trial_billed"] = True
    return user, to_add


def trial_redis_lock_key(user_id: int) -> str:
    return f"sniper:trial:lock:{user_id}"


async def acquire_trial_platform_lock(redis: Any, user_id: int, platform: str) -> str | None:
    """Trial users may only snipe one platform at a time (prevents multi-tab over-use).

    Returns None on success, or the platform that already holds the lock.
    """
    key = trial_redis_lock_key(user_id)
    current = await redis.get(key)
    if current and current != platform:
        return current
    # Refresh TTL for the whole trial window + buffer
    await redis.set(key, platform, ex=TRIAL_LIMIT_SECONDS + 120)
    return None


async def release_trial_platform_lock(redis: Any, user_id: int, platform: str) -> None:
    key = trial_redis_lock_key(user_id)
    current = await redis.get(key)
    if current == platform:
        await redis.delete(key)
