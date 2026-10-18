from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any

import requests
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import SessionLocal, SniperHit, SniperJob
from services.sniper_dispatch import clear_pending_job
from services.user_store import count_names, read_names
from sniper.proxy import DirectIPRotator, ProxyRotator
from sniper.registry import get_checker, get_workers
from sniper.turbo_engine import CheckResult, Status, TurboEngine

# Discord concurrency is derived per proxy line.
# Aim ~6–10 CPS with one line; more pasted providers raise the ceiling.
DISCORD_MIN_WORKERS = 4
DISCORD_MAX_WORKERS = 10
DISCORD_MAX_WORKERS_MULTI = 36
# Shared Free Trial pool — enough for ~4–6 CPS without melting one DataImpulse line.
DISCORD_TRIAL_MAX_WORKERS = 4
# Fair share: longer slots so clients are not bounced to queued every minute.
DISCORD_MAX_SLOT_SECONDS = 180

logger = logging.getLogger(__name__)

_active: dict[str, TurboEngine] = {}
_live_status: dict[str, dict[str, Any]] = {}
_seen_available: dict[str, set[str]] = {}
_ok_times: dict[str, list[float]] = {}
_status_lock = asyncio.Lock()
_flush_tasks: dict[str, asyncio.Task] = {}

REDIS_FLUSH_SEC = 0.15
# Rolling window for dashboard CPS (cumulative average under-reports after late bursts).
_CPS_WINDOW_SEC = 8.0


def _status_key(user_token: str, platform: str) -> str:
    return f"{user_token}:{platform}"


def _redis_status_key(user_token: str, platform: str) -> str:
    return f"sniper:status:{user_token}:{platform}"


def _send_webhook_sync(url: str, payload: dict) -> None:
    try:
        requests.post(url, json=payload, timeout=8)
    except requests.RequestException:
        pass


async def send_webhook(url: str, target: str, platform: str) -> None:
    payload = {
        "username": "UserSniper",
        "embeds": [
            {
                "title": f"Available: {target}",
                "description": f"Platform: **{platform}**",
                "color": 0x57F287,
            }
        ],
    }
    await asyncio.to_thread(_send_webhook_sync, url, payload)


def _default_live_status(platform: str, total_names: int) -> dict[str, Any]:
    return {
        "platform": platform,
        "state": "idle",
        "progress_pct": 0.0,
        "checks_done": 0,
        "total_names": total_names,
        "checks_per_sec": 0.0,
        "valid_checks_per_sec": 0.0,
        "recovery_mode": False,
        "available": 0,
        "occupied": 0,
        "valid_checks": 0,
        "errors": 0,
        "rate_limits": 0,
        "proxy_misses": 0,
        "elapsed_seconds": 0,
        "current_target": None,
        "captures": [],
        "started_at": None,
        "session_id": None,
    }


def _cancel_flush(sk: str) -> None:
    task = _flush_tasks.pop(sk, None)
    if task and not task.done():
        task.cancel()


def clear_live_session(user_token: str, platform: str) -> None:
    """Drop in-memory stats and pending flushes so old workers cannot revive them."""
    sk = _status_key(user_token, platform)
    _cancel_flush(sk)
    _live_status.pop(sk, None)
    _seen_available.pop(sk, None)
    _ok_times.pop(sk, None)
    stop_turbo(user_token, platform)
    _active.pop(sk, None)


def _rolling_cps(sk: str, *, now: float, done: int, elapsed: float) -> float:
    """Prefer recent valid CPS so the UI reflects current speed, not a cold start."""
    times = _ok_times.get(sk) or []
    cutoff = now - _CPS_WINDOW_SEC
    times = [t for t in times if t >= cutoff]
    _ok_times[sk] = times
    if elapsed < 4.0 or len(times) < 4:
        return round(done / max(elapsed, 0.001), 2)
    span = max(now - times[0], 1.0)
    return round(len(times) / min(span, _CPS_WINDOW_SEC), 2)


async def _persist_status(redis: Any, user_token: str, platform: str, payload: dict) -> None:
    key = _redis_status_key(user_token, platform)
    payload = dict(payload)
    try:
        raw = await redis.get(key)
        if raw:
            current = json.loads(raw)
            cur_sid = current.get("session_id")
            pay_sid = payload.get("session_id")
            # Stale worker flush from a previous run must not overwrite a new session.
            if (
                cur_sid
                and pay_sid
                and cur_sid != pay_sid
                and current.get("state") in ("running", "queued", "idle")
            ):
                return
            # Control-API trial billing writes trial_billed_seconds into Redis.
            # Worker flushes must never reset that counter — otherwise the same
            # wall-clock seconds are debited from the trial again on every poll.
            try:
                cur_billed = int(current.get("trial_billed_seconds") or 0)
                pay_billed = int(payload.get("trial_billed_seconds") or 0)
                payload["trial_billed_seconds"] = max(cur_billed, pay_billed)
            except (TypeError, ValueError):
                pass
            if current.get("trial_billed") or payload.get("trial_billed"):
                payload["trial_billed"] = True
            if current.get("running_started_at") and not payload.get("running_started_at"):
                payload["running_started_at"] = current["running_started_at"]
    except Exception:
        pass
    # Never let a stale stop flag zero an active running flush.
    try:
        from services.sniper_queue import is_stop_requested

        if await is_stop_requested(redis, user_token, platform):
            if payload.get("state") not in ("running", "queued"):
                payload["state"] = "idle"
                payload["current_target"] = None
                payload["checks_per_sec"] = 0
                payload["valid_checks_per_sec"] = 0
                payload["recovery_mode"] = False
                # Keep captures / counters — stop must not look like a full reset.
    except Exception:
        pass
    await redis.set(key, json.dumps(payload))


def _schedule_redis_flush(
    redis: Any, user_token: str, platform: str, sk: str
) -> None:
    """Debounce Redis writes — in-memory status stays hot for fast polls."""
    existing = _flush_tasks.get(sk)
    if existing and not existing.done():
        return

    async def _flush() -> None:
        await asyncio.sleep(REDIS_FLUSH_SEC)
        async with _status_lock:
            payload = dict(_live_status.get(sk, {}))
        if payload:
            await _persist_status(redis, user_token, platform, payload)
        _flush_tasks.pop(sk, None)

    _flush_tasks[sk] = asyncio.create_task(_flush())


async def get_live_status(
    redis: Any, user_token: str, platform: str
) -> dict[str, Any] | None:
    sk = _status_key(user_token, platform)
    # Prefer Redis when a stop was requested so UI doesn't stick on "running".
    try:
        from services.sniper_queue import is_stop_requested

        if await is_stop_requested(redis, user_token, platform):
            raw = await redis.get(_redis_status_key(user_token, platform))
            if raw:
                data = json.loads(raw)
                if isinstance(data, dict):
                    data["state"] = "stopped"
                    return data
    except Exception:
        pass

    async with _status_lock:
        if sk in _live_status:
            live = dict(_live_status[sk])
            if live.get("state") != "stopped":
                return live
    raw = await redis.get(_redis_status_key(user_token, platform))
    if raw:
        return json.loads(raw)
    return None


def stop_turbo(
    user_token: str, platform: str, session_id: str | None = None
) -> bool:
    """Stop the in-process turbo engine for this user/platform.

    ``session_id`` is accepted for pubsub/restart fencing compatibility — the
    local engine map is already keyed per user+platform (one active run).
    """
    del session_id  # fencing is handled by Redis status / remote nodes
    sk = _status_key(user_token, platform)
    engine = _active.get(sk)
    if not engine:
        return False
    engine.stop()
    return True


async def mark_status_stopped(redis: Any, user_token: str, platform: str) -> None:
    """Park the session as idle without wiping captures from the last run."""
    sk = _status_key(user_token, platform)
    existing: dict[str, Any] = {}
    async with _status_lock:
        if sk in _live_status:
            existing = dict(_live_status[sk])
    if not existing and redis is not None:
        try:
            raw = await redis.get(_redis_status_key(user_token, platform))
            if raw:
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    existing = parsed
        except Exception:
            pass

    clear_live_session(user_token, platform)
    payload = _default_live_status(platform, int(existing.get("total_names") or 0))
    # Preserve session results so the UI does not flash empty after stop/yield.
    for key in (
        "captures",
        "available",
        "occupied",
        "checks_done",
        "progress_pct",
        "errors",
        "rate_limits",
        "proxy_misses",
        "elapsed_seconds",
        "session_id",
        "started_at",
        "infinite",
    ):
        if key in existing:
            payload[key] = existing[key]
    payload["captures"] = list(existing.get("captures") or [])
    payload["available"] = int(existing.get("available") or len(payload["captures"]) or 0)
    payload["state"] = "idle"
    payload["checks_per_sec"] = 0
    payload["valid_checks_per_sec"] = 0
    payload["recovery_mode"] = False
    payload["current_target"] = None
    async with _status_lock:
        _live_status[sk] = dict(payload)
    await _persist_status(redis, user_token, platform, payload)


async def mark_job_running(
    redis: Any,
    user_token: str,
    platform: str,
    *,
    node_id: str | None = None,
    targets_count: int = 0,
    session_id: str | None = None,
) -> None:
    """Worker picked up a queued job — flip UI off 'queued' before heavy name loading."""
    sk = _status_key(user_token, platform)
    key = _redis_status_key(user_token, platform)
    existing: dict[str, Any] = {}
    try:
        raw = await redis.get(key)
        if raw:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                existing = parsed
    except Exception:
        pass

    payload = _default_live_status(platform, targets_count or int(existing.get("total_names") or 0))
    payload.update(existing)
    payload["state"] = "running"
    payload["running_started_at"] = time.time()
    if existing.get("state") == "queued":
        payload["trial_billed_seconds"] = 0
        payload["trial_billed"] = False
    payload["checks_done"] = int(existing.get("checks_done") or 0)
    payload["checks_per_sec"] = 0
    payload["valid_checks_per_sec"] = 0
    payload["current_target"] = None
    if node_id:
        payload["node_id"] = node_id
    if session_id and not existing.get("session_id"):
        payload["session_id"] = session_id
    elif existing.get("session_id"):
        # Keep stable session across fair-share requeues (do not overwrite with job_id).
        payload["session_id"] = existing["session_id"]
    elif session_id:
        payload["session_id"] = session_id
    if not payload.get("started_at"):
        payload["started_at"] = time.time()

    async with _status_lock:
        _live_status[sk] = dict(payload)
    await _persist_status(redis, user_token, platform, payload)
    await clear_pending_job(redis, user_token, platform)


async def run_turbo_job(
    *,
    job_id: str,
    user_id: int,
    user_token: str,
    platform: str,
    targets: list[str] | None = None,
    proxy_lines: list[str],
    webhook_url: str | None,
    workers: int,
    redis: Any,
    infinite: bool = False,
    load_targets_from_file: bool = False,
    load_targets_from_redis: bool = False,
    targets_count: int | None = None,
    node_id: str | None = None,
    rotate_sessions: bool = False,
    session_id: str | None = None,
) -> None:
    sk = _status_key(user_token, platform)
    clear_live_session(user_token, platform)

    if targets_count is None:
        if targets:
            targets_count = len(targets)
        else:
            targets_count = await asyncio.to_thread(count_names, user_token)

    effective_session = session_id or job_id
    await mark_job_running(
        redis,
        user_token,
        platform,
        node_id=node_id,
        targets_count=targets_count or 0,
        session_id=effective_session,
    )

    if load_targets_from_redis and redis is not None:
        from services.sniper_queue import load_names_from_redis

        targets = await load_names_from_redis(redis, user_token)
    elif load_targets_from_file or not targets:
        targets = await asyncio.to_thread(read_names, user_token)
    if not targets:
        logger.error("No names for job %s (user %s)", job_id, user_token[:8])
        await mark_status_stopped(redis, user_token, platform)
        async with SessionLocal() as db:
            await db.execute(
                update(SniperJob).where(SniperJob.id == job_id).values(status="error")
            )
            await db.commit()
        return

    total = len(targets)
    session_id = effective_session
    queue_started_at = time.time()
    running_started_at = time.time()
    if redis is not None:
        try:
            raw = await redis.get(_redis_status_key(user_token, platform))
            if raw:
                prev = json.loads(raw)
                if isinstance(prev, dict):
                    session_id = str(prev.get("session_id") or effective_session)
                    if prev.get("started_at"):
                        queue_started_at = float(prev["started_at"])
        except Exception:
            pass

    status = _default_live_status(platform, total)
    status["state"] = "running"
    status["started_at"] = queue_started_at
    status["running_started_at"] = running_started_at
    status["session_id"] = session_id
    status["infinite"] = bool(infinite)
    if node_id:
        status["node_id"] = node_id
    # Carry captures / counters across fair-share requeues of the same session.
    if redis is not None:
        try:
            raw = await redis.get(_redis_status_key(user_token, platform))
            if raw:
                prev = json.loads(raw)
                if isinstance(prev, dict) and str(prev.get("session_id") or "") == str(session_id):
                    for key in (
                        "captures",
                        "available",
                        "occupied",
                        "checks_done",
                        "progress_pct",
                        "errors",
                        "rate_limits",
                        "proxy_misses",
                        "elapsed_seconds",
                    ):
                        if key in prev:
                            status[key] = prev[key]
        except Exception:
            pass
    async with _status_lock:
        _live_status[sk] = status
    if redis is not None:
        from services.sniper_queue import clear_stop_flag

        await clear_stop_flag(redis, user_token, platform)
    await _persist_status(redis, user_token, platform, status)

    lines = [ln for ln in (proxy_lines or []) if str(ln).strip()]
    if lines:
        rotator: ProxyRotator | DirectIPRotator = ProxyRotator.from_lines(
            lines, rotate_sessions=rotate_sessions
        )
    else:
        # Datacenter direct mode — no proxy lines: use the machine's own IP(s).
        src = [ip for ip in (settings.sniper_source_ips or "").split(",") if ip.strip()]
        rotator = DirectIPRotator(source_ips=src)
        logger.info("No proxy lines — datacenter direct mode, source_ips=%s", len(src))
    checker = get_checker(platform)
    if checker is None:
        logger.error("No turbo checker for platform %s", platform)
        return

    effective_workers = get_workers(platform, workers)
    if platform == "discord":
        # Each pasted line is an independent provider — budget stacks, and the
        # hard cap rises with line count so Flash+DataImpulse+Adam can run in parallel.
        if rotate_sessions:
            # Free Trial shares one residential line across many users.
            cap = min(effective_workers, rotator.workers_budget, DISCORD_TRIAL_MAX_WORKERS)
            effective_workers = max(1, cap)
        else:
            line_cap = min(
                DISCORD_MAX_WORKERS_MULTI,
                max(DISCORD_MAX_WORKERS, rotator.line_count * 6),
            )
            cap = min(effective_workers, rotator.workers_budget, line_cap)
            effective_workers = max(DISCORD_MIN_WORKERS, cap)
        logger.info(
            "Discord turbo workers=%s budget=%s lines=%s rotate_sessions=%s requested=%s",
            effective_workers,
            rotator.workers_budget,
            rotator.line_count,
            rotate_sessions,
            workers,
        )

    stop_reason = "complete"

    async def should_stop() -> bool:
        nonlocal stop_reason
        if redis is None:
            return False
        try:
            from services.sniper_queue import is_stop_requested

            if await is_stop_requested(redis, user_token, platform):
                stop_reason = "user_stop"
                return True
        except Exception:
            pass
        # Discord fair-share: free the slot when Redis has real waiters, then requeue.
        if platform == "discord" and running_started_at:
            elapsed_run = time.time() - running_started_at
            if elapsed_run >= DISCORD_MAX_SLOT_SECONDS:
                try:
                    from sniper.vps_pools import QUEUE_KEYS

                    # Only count jobs actually waiting in Redis — scanning status for
                    # "queued" caused a yield storm (everyone bounced every slot).
                    waiting = 0
                    for key in (QUEUE_KEYS["vps1"], QUEUE_KEYS["vps2"]):
                        waiting += int(await redis.llen(key) or 0)
                    if waiting > 0:
                        logger.info(
                            "Discord slot yield job=%s after %.0fs (%s waiting in queue)",
                            job_id,
                            elapsed_run,
                            waiting,
                        )
                        stop_reason = "yield"
                        return True
                except Exception:
                    pass
        return False

    async def on_available(result: CheckResult) -> None:
        capture = {"name": result.target, "at": datetime.now(timezone.utc).isoformat()}
        async with _status_lock:
            live = _live_status.get(sk, status)
            live["captures"] = (live.get("captures") or [])[-199:] + [capture]
            live["available"] = int(live.get("available") or 0) + 1
        async with SessionLocal() as db:
            db.add(
                SniperHit(
                    job_id=job_id,
                    user_id=user_id,
                    platform=result.platform,
                    target=result.target,
                    status=result.status.value,
                )
            )
            await db.commit()
        if webhook_url:
            await send_webhook(webhook_url, result.target, result.platform)
        if redis:
            await redis.publish(
                f"sniper:{user_token}",
                json.dumps(
                    {"type": "hit", "target": result.target, "platform": result.platform}
                ),
            )

    async def on_result(result: CheckResult) -> None:
        # Honor durable stop flag mid-run (distributed control plane).
        if await should_stop():
            stop_turbo(user_token, platform)
            async with _status_lock:
                live = _live_status.get(sk)
                if live is not None:
                    live["state"] = "stopped"
                    live["current_target"] = None
                    live["checks_per_sec"] = 0
                    live["valid_checks_per_sec"] = 0
            return
        async with _status_lock:
            live = _live_status.setdefault(sk, _default_live_status(platform, total))
            live["current_target"] = result.target
            if result.status == Status.PROXY_LATE:
                # Proxy miss — count it, but do not advance name progress / CPS.
                live["proxy_misses"] = int(live.get("proxy_misses") or 0) + 1
                if result.detail:
                    live["last_proxy_error"] = str(result.detail)[:120]
            elif result.status == Status.RATE_LIMITED:
                live["rate_limits"] = int(live.get("rate_limits") or 0) + 1
            elif result.status in (Status.BLOCKED, Status.ERROR):
                live["errors"] = int(live.get("errors") or 0) + 1
            else:
                # AVAILABLE / TAKEN only — real progress.
                live["checks_done"] = int(live.get("checks_done") or 0) + 1
                if result.status == Status.TAKEN:
                    live["occupied"] = int(live.get("occupied") or 0) + 1
                _ok_times.setdefault(sk, []).append(time.time())
            elapsed = max(time.time() - running_started_at, 0.001)
            done = int(live["checks_done"])
            attempts = (
                done
                + int(live.get("rate_limits") or 0)
                + int(live.get("errors") or 0)
                + int(live.get("proxy_misses") or 0)
            )
            live["elapsed_seconds"] = int(elapsed)
            live["checks_per_sec"] = _rolling_cps(
                sk, now=time.time(), done=done, elapsed=elapsed
            )
            live["valid_checks_per_sec"] = live["checks_per_sec"]
            fail = int(live.get("rate_limits") or 0) + int(live.get("errors") or 0)
            live["fail_pct"] = round(100.0 * fail / max(done + fail, 1), 2)
            live["attempt_cps"] = round(attempts / elapsed, 2)
            # Only when rolling CPS is dead AND failures dominate — late alone
            # is normal on rotating residential and must not scare the UI.
            rl_n = int(live.get("rate_limits") or 0)
            late_n = int(live.get("proxy_misses") or 0)
            err_n = int(live.get("errors") or 0)
            live["recovery_mode"] = live["checks_per_sec"] < 1.5 and (
                rl_n > int(live.get("checks_done") or 0) * 3
                or (
                    late_n > max(400, int(live.get("checks_done") or 0) * 10)
                    and live["checks_per_sec"] < 1.0
                )
            )
            if live["recovery_mode"]:
                if rl_n >= late_n and rl_n >= err_n and rl_n > 0:
                    live["degrade_reason"] = "rate_limit"
                else:
                    live["degrade_reason"] = "late"
            else:
                live["degrade_reason"] = None
            if total > 0:
                # For infinite mode, progress is modulo one pass.
                live["progress_pct"] = min(100.0, round((done % total) / total * 100, 2)) if infinite else min(
                    100.0, round(done / total * 100, 2)
                )
        _schedule_redis_flush(redis, user_token, platform, sk)

    # Abort before starting if stop was already requested (queued-job race).
    if redis is not None:
        try:
            from services.sniper_queue import is_stop_requested

            if await is_stop_requested(redis, user_token, platform):
                await mark_status_stopped(redis, user_token, platform)
                async with SessionLocal() as db:
                    await db.execute(
                        update(SniperJob)
                        .where(SniperJob.id == job_id)
                        .values(status="stopped")
                    )
                    await db.commit()
                return
        except Exception:
            pass

    # Discord + Guns: fresh provider session every request. Sticky exits pile up 429s.
    use_sticky_slots = rotator.rotate_sessions and platform not in ("discord", "guns")
    engine = TurboEngine(
        checker=checker,
        rotate_proxy=rotator.next_url,
        workers=effective_workers,
        proxy_for_slot=rotator.url_for_slot if use_sticky_slots else None,
        lease_proxy=None if use_sticky_slots else rotator.next_lease,
        report_proxy=None if use_sticky_slots else rotator.report,
        on_available=on_available,
        on_result=on_result,
        should_stop=should_stop,
    )
    _active[job_id] = engine
    _active[sk] = engine

    # Re-check after registration — stop may have arrived during setup.
    if redis is not None:
        try:
            from services.sniper_queue import is_stop_requested

            if await is_stop_requested(redis, user_token, platform):
                engine.stop()
        except Exception:
            pass

    final_state = "stopped"
    stats_payload: dict[str, Any] = {}
    try:
        async with SessionLocal() as db:
            await db.execute(
                update(SniperJob).where(SniperJob.id == job_id).values(status="running")
            )
            await db.commit()

        # Keep checking until Stop. Infinite mode restarts the list when done.
        while True:
            if await should_stop():
                final_state = "stopped"
                break
            stats = await engine.run(targets)
            stats_payload = stats.to_dict()
            if engine._stop.is_set():
                final_state = "stopped"
                break
            if not infinite:
                final_state = "completed"
                stop_reason = "complete"
                break
            # Infinite: reset progress cursor by running the list again.
            if await should_stop():
                final_state = "stopped"
                break
    except Exception:
        logger.exception("Turbo job %s failed", job_id)
        final_state = "interrupted"
        stop_reason = "error"
    finally:
        _active.pop(job_id, None)
        _active.pop(sk, None)
        async with _status_lock:
            live = dict(_live_status.get(sk) or status)

        if stop_reason == "yield" and redis is not None:
            # Fair-share: park as queued, keep captures, and re-enter the fleet queue.
            payload = dict(live)
            payload["state"] = "queued"
            payload["checks_per_sec"] = 0
            payload["valid_checks_per_sec"] = 0
            payload["recovery_mode"] = False
            payload["current_target"] = None
            payload["session_id"] = session_id
            payload["total_names"] = total
            async with _status_lock:
                _live_status[sk] = dict(payload)
            await _persist_status(redis, user_token, platform, payload)

            new_job_id = str(uuid.uuid4())
            job_payload = {
                "job_id": new_job_id,
                "user_id": user_id,
                "user_token": user_token,
                "platform": platform,
                "targets": None if (load_targets_from_file or load_targets_from_redis) else targets,
                "targets_count": total,
                "load_targets_from_file": bool(load_targets_from_file),
                "load_targets_from_redis": bool(load_targets_from_redis),
                "proxy_lines": proxy_lines,
                "webhook_url": webhook_url,
                "workers": workers,
                "infinite": bool(infinite),
                "rotate_sessions": bool(rotate_sessions),
            }
            try:
                from services.sniper_dispatch import publish_dispatch, store_pending_job
                from services.sniper_queue import clear_stop_flag, enqueue_sniper_job

                await clear_stop_flag(redis, user_token, platform)
                await store_pending_job(redis, user_token, platform, job_payload)
                await enqueue_sniper_job(redis, platform, job_payload)
                await publish_dispatch(redis, job_payload)
                logger.info(
                    "Requeued Discord job after fair-share yield session=%s new_job=%s",
                    session_id,
                    new_job_id,
                )
            except Exception:
                logger.exception("Failed to requeue after fair-share yield")
                await mark_status_stopped(redis, user_token, platform)
            db_status = "queued"
        else:
            # Soft idle — keep captures / counters so the dashboard does not reset.
            payload = dict(live)
            payload["state"] = (
                "idle" if final_state in ("stopped", "completed") else final_state
            )
            if final_state == "completed":
                payload["state"] = "completed"
            payload["checks_per_sec"] = 0
            payload["valid_checks_per_sec"] = 0
            payload["recovery_mode"] = False
            payload["current_target"] = None
            async with _status_lock:
                _live_status[sk] = dict(payload)
            await _persist_status(redis, user_token, platform, payload)
            db_status = final_state

        async with SessionLocal() as db:
            await db.execute(
                update(SniperJob)
                .where(SniperJob.id == job_id)
                .values(status=db_status, stats=stats_payload or None)
            )
            await db.commit()


async def create_job_record(
    db: AsyncSession,
    *,
    user_id: int,
    user_token: str,
    platform: str,
    targets: list[str],
    proxy_line: str,
    webhook_url: str | None,
    workers: int,
) -> str:
    job_id = str(uuid.uuid4())
    db.add(
        SniperJob(
            id=job_id,
            user_id=user_id,
            user_token=user_token,
            platform=platform,
            targets=targets,
            proxy=proxy_line,
            webhook_url=webhook_url,
            workers=workers,
            status="idle",
        )
    )
    await db.commit()
    return job_id
