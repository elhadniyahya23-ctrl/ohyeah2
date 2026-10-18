import asyncio
import json
import time
import uuid
from datetime import datetime
from enum import Enum

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import User, get_db
from deps import get_current_user, user_storage_token
from sqlalchemy import delete, select

from database import SniperHit
from services.plans import (
    is_trial_user,
    plan_payload,
    trial_exhausted,
    trial_remaining_seconds,
    user_has_active_plan,
)
from services.trial_billing import (
    acquire_trial_platform_lock,
    bill_trial_progress,
    release_trial_platform_lock,
    session_elapsed,
)
from services.trial_proxies import get_trial_proxies, user_can_manage_proxies
from services.turbo_sniper_service import (
    create_job_record,
    get_live_status,
    run_turbo_job,
)
from services.sniper_queue import (
    clear_stop_flag,
    enqueue_sniper_job,
    pick_least_busy_pool,
    prepare_sniper_restart,
    request_sniper_stop,
    store_names_in_redis,
)
from services.sniper_dispatch import (
    is_stuck_starting,
    maybe_start_overflow_job,
    publish_dispatch,
    store_pending_job,
)
from sniper.registry import COMING_SOON_PLATFORMS, TURBO_PLATFORMS, get_workers
from sniper.vps_pools import is_remote_pool, pools_for_platform
from services.user_store import (
    count_names,
    normalize_proxy_lines,
    read_names,
    read_proxies,
    write_proxies,
)
from services.user_store import read_settings

router = APIRouter()


class Platform(str, Enum):
    discord = "discord"
    roblox = "roblox"
    minecraft = "minecraft"
    telegram = "telegram"
    whatsapp = "whatsapp"
    instagram = "instagram"
    tiktok = "tiktok"
    guns = "guns"
    snapchat = "snapchat"
    github = "github"
    reddit = "reddit"
    youtube = "youtube"
    epic = "epic"
    ubisoft = "ubisoft"
    twitter = "twitter"
    steam = "steam"


class SniperStartRequest(BaseModel):
    platform: Platform
    names: list[str] = Field(default_factory=list)
    proxies: list[str] = Field(default_factory=list)
    mode: str = "sequential"
    # When true, keep cycling the name list forever until Stop (or trial ends).
    infinite: bool = False


class SniperStatus(BaseModel):
    platform: Platform
    state: str
    progress_pct: float
    checks_done: int
    total_names: int
    checks_per_sec: float
    valid_checks_per_sec: float = 0.0
    recovery_mode: bool = False
    available: int
    occupied: int
    errors: int
    rate_limits: int
    proxy_misses: int
    elapsed_seconds: int
    current_target: str | None
    captures: list[dict]
    trial_remaining_seconds: int | None = None
    trial_exhausted: bool = False
    redirect_to_payment: bool = False
    infinite: bool = False


def default_status(platform: Platform) -> dict:
    return {
        "platform": platform.value,
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
        "trial_remaining_seconds": None,
        "trial_exhausted": False,
        "redirect_to_payment": False,
        "infinite": False,
    }


def fresh_run_status(
    platform: Platform,
    *,
    total_names: int = 0,
    state: str = "idle",
    infinite: bool = False,
    trial_remaining_seconds: int | None = None,
    trial_exhausted: bool = False,
    redirect_to_payment: bool = False,
    session_id: str | None = None,
) -> dict:
    """Zeroed session counters — each Start/Stop begins a clean slate."""
    status = default_status(platform)
    status["state"] = state
    status["total_names"] = total_names
    status["infinite"] = infinite
    status["trial_remaining_seconds"] = trial_remaining_seconds
    status["trial_exhausted"] = trial_exhausted
    status["redirect_to_payment"] = redirect_to_payment
    status["session_id"] = session_id
    return status


def _scrub_to_current_session(data: dict) -> dict:
    """Drop captures and counters that predate this run's started_at."""
    data = dict(data)
    started = data.get("started_at")
    if not started:
        return data
    try:
        started_ts = float(started)
    except (TypeError, ValueError):
        return data

    captures: list[dict] = []
    for cap in data.get("captures") or []:
        at = cap.get("at")
        if not at:
            continue
        try:
            cap_ts = datetime.fromisoformat(str(at).replace("Z", "+00:00")).timestamp()
        except ValueError:
            continue
        if cap_ts >= started_ts - 1:
            captures.append(cap)
    data["captures"] = captures
    data["available"] = len(captures)
    return data


def _redis_key(user_token: str, platform: str) -> str:
    return f"sniper:status:{user_token}:{platform}"


async def _force_stop_for_trial(
    request: Request,
    token: str,
    platform: str,
    data: dict,
    *,
    user_id: int | None = None,
) -> dict:
    await request_sniper_stop(request.app.state.redis, token, platform)
    if user_id is not None:
        await release_trial_platform_lock(request.app.state.redis, user_id, platform)
    return {
        **fresh_run_status(
            Platform(platform),
            redirect_to_payment=True,
            trial_exhausted=True,
        ),
        "elapsed_seconds": session_elapsed(data),
    }


async def _load_saved_captures(db: AsyncSession, user_id: int, platform: str, limit: int = 200) -> list[dict]:
    result = await db.execute(
        select(SniperHit)
        .where(SniperHit.user_id == user_id, SniperHit.platform == platform, SniperHit.status == "available")
        .order_by(SniperHit.id.desc())
        .limit(limit)
    )
    hits = list(result.scalars().all())
    hits.reverse()
    return [
        {
            "name": h.target,
            "at": h.created_at.isoformat() if h.created_at else None,
        }
        for h in hits
    ]


def _session_is_stuck(data: dict) -> bool:
    """No checks after start — worker never picked up the job."""
    return is_stuck_starting(data)


@router.post("/start")
async def start_sniper(
    body: SniperStartRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if settings.local_safe_mode:
        raise HTTPException(
            403,
            "Local safe mode is enabled: live sniping is disabled on localhost.",
        )

    if trial_exhausted(user) or (
        (user.rank or "").lower().find("expired") >= 0 and "trial" in (user.rank or "").lower()
    ):
        raise HTTPException(
            403,
            "Free trial ended — upgrade on the Shop page to keep sniping.",
        )
    if not user_has_active_plan(user):
        raise HTTPException(403, "Your plan has expired. Please upgrade to continue.")

    if body.platform.value not in TURBO_PLATFORMS:
        if body.platform.value in COMING_SOON_PLATFORMS:
            raise HTTPException(
                501,
                f"{body.platform.value} sniper is in development — use Discord, Roblox, MC, "
                "Instagram, TikTok, GitHub, Reddit, or Guns.lol for now",
            )
        raise HTTPException(501, f"{body.platform.value} sniper is not available yet")

    token = user_storage_token(user)

    # Pick pool before loading names so remote fleets get Redis-backed lists.
    vps_pool = await pick_least_busy_pool(
        request.app.state.redis, body.platform.value
    )
    load_targets_from_file = False
    load_targets_from_redis = False
    multi_pool = len(pools_for_platform(body.platform.value)) > 1
    if body.names:
        targets = [n.strip() for n in body.names if n.strip()]
        name_count = len(targets)
        if multi_pool or is_remote_pool(vps_pool):
            await store_names_in_redis(request.app.state.redis, token, targets)
            targets = []
            load_targets_from_redis = True
    else:
        name_count = await asyncio.to_thread(count_names, token)
        if name_count == 0:
            raise HTTPException(400, "No names loaded")
        # Multi-pool Discord (and any remote pool) shares names via Redis so Vultr
        # nodes can run without the Hostinger data volume.
        if multi_pool or is_remote_pool(vps_pool):
            targets = await asyncio.to_thread(read_names, token)
            await store_names_in_redis(request.app.state.redis, token, targets)
            targets = []
            load_targets_from_redis = True
            load_targets_from_file = False
        else:
            targets = []
            load_targets_from_file = True

    if name_count == 0:
        raise HTTPException(400, "No names loaded")

    # Free Trial uses shared system proxies. Paid users must bring their own.
    if is_trial_user(user):
        proxies = get_trial_proxies()
        if not proxies:
            raise HTTPException(
                503,
                "Trial proxies are not configured yet — set TRIAL_PROXY_LINES on the API.",
            )
    else:
        proxies = normalize_proxy_lines(body.proxies) if body.proxies else []
        if proxies:
            if not user_can_manage_proxies(user):
                raise HTTPException(403, "Upgrade to manage your own proxies")
            await asyncio.to_thread(write_proxies, token, proxies)
        else:
            proxies = await asyncio.to_thread(read_proxies, token)
        if not proxies:
            raise HTTPException(400, "Add at least one proxy in the Proxies tab")

    existing = await get_live_status(request.app.state.redis, token, body.platform.value)
    if existing and existing.get("state") in ("running", "queued"):
        if existing.get("state") == "running" and int(existing.get("checks_done") or 0) > 0:
            raise HTTPException(409, "Sniper already active for this platform")
        if not _session_is_stuck(existing):
            raise HTTPException(409, "Sniper already active for this platform")

    # Wind down any prior worker without poisoning the next run with a stop flag.
    await prepare_sniper_restart(request.app.state.redis, token, body.platform.value)
    await clear_stop_flag(request.app.state.redis, token, body.platform.value)

    # Trial: only one platform at a time, and bill any leftover from a previous session.
    if is_trial_user(user):
        held = await acquire_trial_platform_lock(
            request.app.state.redis, user.id, body.platform.value
        )
        if held:
            raise HTTPException(
                409,
                f"Free Trial can only snipe one platform at a time — stop {held} first.",
            )

    user_settings = await asyncio.to_thread(read_settings, token)
    webhook_url = (user_settings.get("webhook_url") or "").strip() or None

    worker_count = get_workers(body.platform.value, settings.turbo_workers)
    infinite = bool(body.infinite)

    job_id = await create_job_record(
        db,
        user_id=user.id,
        user_token=token,
        platform=body.platform.value,
        targets=targets,
        proxy_line=proxies[0],
        webhook_url=webhook_url,
        workers=worker_count,
    )

    trial_remaining = (
        trial_remaining_seconds(user) if is_trial_user(user) else None
    )
    session_id = str(uuid.uuid4())
    # Distributed jobs wait for a free sniper-node; keep Redis state honest so
    # trial billing and stuck-start recovery do not treat queue wait as running.
    initial_state = "queued" if settings.sniper_distributed else "running"
    status = fresh_run_status(
        body.platform,
        total_names=name_count,
        state=initial_state,
        infinite=infinite,
        trial_remaining_seconds=trial_remaining,
        session_id=session_id,
    )
    status["started_at"] = time.time()
    if not settings.sniper_distributed:
        status["running_started_at"] = time.time()
    status["vps_pool"] = vps_pool
    status["trial_billed_seconds"] = 0
    status["trial_billed"] = False
    await request.app.state.redis.set(_redis_key(token, body.platform.value), json.dumps(status))

    job_payload = {
        "job_id": job_id,
        "user_id": user.id,
        "user_token": token,
        "platform": body.platform.value,
        "targets": targets,
        "targets_count": name_count,
        "load_targets_from_file": load_targets_from_file,
        "load_targets_from_redis": load_targets_from_redis,
        "proxy_lines": proxies,
        "webhook_url": webhook_url,
        "workers": worker_count,
        "infinite": infinite,
        "rotate_sessions": is_trial_user(user),
        "vps_pool": vps_pool,
    }

    if settings.sniper_distributed:
        await store_pending_job(
            request.app.state.redis, token, body.platform.value, job_payload
        )
        await enqueue_sniper_job(
            request.app.state.redis,
            body.platform.value,
            job_payload,
            pool=vps_pool,
        )
        await publish_dispatch(request.app.state.redis, job_payload)
    else:
        asyncio.create_task(
            run_turbo_job(
                redis=request.app.state.redis,
                load_targets_from_file=load_targets_from_file,
                load_targets_from_redis=load_targets_from_redis,
                targets_count=name_count,
                **{
                    k: v
                    for k, v in job_payload.items()
                    if k
                    not in (
                        "load_targets_from_file",
                        "load_targets_from_redis",
                        "targets_count",
                        "vps_pool",
                    )
                },
            )
        )

    return {
        "ok": True,
        "platform": body.platform.value,
        "total_names": name_count,
        "job_id": job_id,
        "resumed": False,
        "infinite": infinite,
        "trial_remaining_seconds": status["trial_remaining_seconds"],
    }


@router.post("/stop")
async def stop_sniper(
    platform: Platform,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    token = user_storage_token(user)
    await request_sniper_stop(request.app.state.redis, token, platform.value)
    await release_trial_platform_lock(request.app.state.redis, user.id, platform.value)

    raw = await request.app.state.redis.get(_redis_key(token, platform.value))
    if raw:
        data = json.loads(raw)
        data["elapsed_seconds"] = session_elapsed(data)
        user, _ = await bill_trial_progress(db, user, data, force_complete=True)

    plan = plan_payload(user)
    status = fresh_run_status(
        platform,
        trial_remaining_seconds=plan["trial_remaining_seconds"],
        trial_exhausted=plan["trial_exhausted"],
        redirect_to_payment=bool(plan["trial_exhausted"]),
    )
    await request.app.state.redis.set(_redis_key(token, platform.value), json.dumps(status))
    return {"ok": True, **plan}


@router.post("/reset")
async def reset_sniper(
    platform: Platform,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    token = user_storage_token(user)
    raw = await request.app.state.redis.get(_redis_key(token, platform.value))
    data = json.loads(raw) if raw else default_status(platform)
    # Always bill before wiping Redis so F5/reset cannot erase trial usage.
    if is_trial_user(user) and data.get("state") == "running":
        data["elapsed_seconds"] = session_elapsed(data)
        user, _ = await bill_trial_progress(db, user, data, force_complete=True)
    await request_sniper_stop(request.app.state.redis, token, platform.value)
    await release_trial_platform_lock(request.app.state.redis, user.id, platform.value)
    plan = plan_payload(user)
    status = fresh_run_status(
        platform,
        trial_remaining_seconds=plan["trial_remaining_seconds"],
        trial_exhausted=plan["trial_exhausted"],
        redirect_to_payment=bool(plan["trial_exhausted"]),
    )
    await request.app.state.redis.set(_redis_key(token, platform.value), json.dumps(status))
    return {"ok": True, **plan}


@router.post("/pause")
async def pause_sniper(platform: Platform, user: User = Depends(get_current_user)):
    raise HTTPException(501, "Pause not supported in turbo mode — use Stop")


@router.post("/resume")
async def resume_sniper(platform: Platform, user: User = Depends(get_current_user)):
    raise HTTPException(501, "Resume not supported in turbo mode — press Start again")


@router.get("/status", response_model=SniperStatus)
async def get_status(
    platform: Platform,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    token = user_storage_token(user)
    data = await get_live_status(request.app.state.redis, token, platform.value)
    plan = plan_payload(user)

    if not data or data.get("state") not in ("running", "queued"):
        # Keep last-run captures/counters visible — do not wipe the dashboard on stop.
        if data and isinstance(data, dict):
            status = default_status(platform)
            for key in status:
                if key in data and data[key] is not None:
                    status[key] = data[key]
            status["state"] = "completed" if data.get("state") == "completed" else "idle"
            status["checks_per_sec"] = 0
            status["valid_checks_per_sec"] = 0
            status["recovery_mode"] = False
            status["current_target"] = None
            status["trial_remaining_seconds"] = plan["trial_remaining_seconds"]
            status["trial_exhausted"] = plan["trial_exhausted"]
            status["redirect_to_payment"] = bool(plan["trial_exhausted"])
            status["captures"] = list(data.get("captures") or [])
            status["available"] = int(
                data.get("available") or len(status["captures"]) or 0
            )
            return SniperStatus(**status)
        status = fresh_run_status(
            platform,
            trial_remaining_seconds=plan["trial_remaining_seconds"],
            trial_exhausted=plan["trial_exhausted"],
            redirect_to_payment=bool(plan["trial_exhausted"]),
        )
        return SniperStatus(**status)

    data = dict(data)
    original_state = (data.get("state") or "idle").lower()
    # UI shows queued jobs as running, but billing must use the real state —
    # otherwise started_at (queue time) burns the Free Trial.
    if data.get("state") in ("running", "queued"):
        await maybe_start_overflow_job(
            request.app.state.redis, token, platform.value, data
        )
        data = _scrub_to_current_session(data)
        billing_view = dict(data)
        billing_view["state"] = original_state
        data["elapsed_seconds"] = session_elapsed(billing_view)
        plan = plan_payload(user)

        # Expired trial / lapsed paid plan must not keep burning proxies mid-run.
        # (is_trial_user is False once rank is "Free Trial Expired", so billing alone
        # would never stop those sessions.)
        if not user_has_active_plan(user):
            data = await _force_stop_for_trial(
                request, token, platform.value, data, user_id=user.id
            )
            data["trial_remaining_seconds"] = plan["trial_remaining_seconds"]
            data["trial_exhausted"] = True
            data["redirect_to_payment"] = True
            await request.app.state.redis.set(
                _redis_key(token, platform.value), json.dumps(data)
            )
            return SniperStatus(**data)

        if is_trial_user(user):
            # Persist trial seconds to DB on every poll — F5 cannot wipe usage.
            user, _ = await bill_trial_progress(
                db, user, billing_view, force_complete=False
            )
            # Keep billing counters on the response/redis payload.
            data["trial_billed_seconds"] = billing_view.get("trial_billed_seconds", 0)
            data["trial_billed"] = billing_view.get("trial_billed", False)
            remaining = trial_remaining_seconds(user)
            if remaining <= 0:
                data = await _force_stop_for_trial(
                    request, token, platform.value, data, user_id=user.id
                )
                plan = plan_payload(user)
                data["trial_remaining_seconds"] = plan["trial_remaining_seconds"]
                data["trial_exhausted"] = True
                data["redirect_to_payment"] = True
            else:
                data["trial_remaining_seconds"] = remaining
                data["trial_exhausted"] = False
                data["redirect_to_payment"] = False
            await request.app.state.redis.set(
                _redis_key(token, platform.value), json.dumps(data)
            )
            # Refresh trial lock TTL while running
            await acquire_trial_platform_lock(
                request.app.state.redis, user.id, platform.value
            )
        else:
            data["trial_remaining_seconds"] = plan["trial_remaining_seconds"]
            data["trial_exhausted"] = plan["trial_exhausted"]
            data["redirect_to_payment"] = bool(plan["trial_exhausted"])

    # Keep queued honest — UI must show "queued", not fake "running/starting".
    return SniperStatus(**data)


@router.get("/results")
async def list_results(
    platform: Platform | None = None,
    limit: int = 300,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Persistent captures from DB (survives refresh / new sniper runs)."""
    limit = max(1, min(limit, 1000))
    query = (
        select(SniperHit)
        .where(SniperHit.user_id == user.id, SniperHit.status == "available")
        .order_by(SniperHit.id.desc())
        .limit(limit)
    )
    if platform is not None:
        query = query.where(SniperHit.platform == platform.value)
    result = await db.execute(query)
    hits = list(result.scalars().all())
    return {
        "count": len(hits),
        "results": [
            {
                "name": h.target,
                "platform": h.platform,
                "at": h.created_at.isoformat() if h.created_at else None,
                "job_id": h.job_id,
            }
            for h in hits
        ],
    }


@router.delete("/captures")
async def clear_captures(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    token = user_storage_token(user)
    cleared = 0
    for platform in Platform:
        key = _redis_key(token, platform.value)
        raw = await request.app.state.redis.get(key)
        if not raw:
            continue
        data = json.loads(raw)
        if data.get("captures"):
            data["captures"] = []
            data["available"] = 0
            await request.app.state.redis.set(key, json.dumps(data))
            cleared += 1
    # Also clear durable DB hits so Results stays consistent.
    await db.execute(delete(SniperHit).where(SniperHit.user_id == user.id))
    await db.commit()
    return {"ok": True, "cleared": cleared}
