"""Admin-only control plane: users, live snipers, overview stats."""

from __future__ import annotations

import asyncio
import shutil
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from database import PaymentOrder, SniperHit, SniperJob, User, AdminAuditLog, get_db
from deps import get_current_user
from services.admin_audit import audit_row, record_admin_action
from services.sniper_queue import request_sniper_stop
from services.sniper_cleanup import cleanup_live_snipers, scan_status_keys
from services.trial_proxies import get_trial_proxies, user_can_manage_proxies
from services.user_store import count_names, read_proxies, read_settings, user_dir, write_proxies
from services.settings_defaults import merge_settings
from services.request_utils import client_ip
from services.plans import (
    ADMIN_USERNAMES,
    _owner_tokens,
    activate_plan,
    is_admin,
    is_admin_username,
    plan_payload,
    utc_now,
)

router = APIRouter()

GRANTABLE_PLANS = {
    "premium-1-week": {"rank": "Premium", "duration_days": 7, "label": "7-Day Pass"},
    "premium-1-month": {"rank": "Premium", "duration_days": 30, "label": "1 Month"},
    "premium-lifetime": {"rank": "Lifetime", "duration_days": None, "label": "Lifetime"},
    "premium-custom": {"rank": "Premium", "duration_days": None, "label": "Custom"},
}


def _require_admin(user: User) -> None:
    if not is_admin(user):
        raise HTTPException(403, "Admin only")


def _user_row(user: User) -> dict:
    payload = plan_payload(user)
    return {
        "id": user.id,
        "username": user.username,
        "rank": user.rank,
        "has_active_plan": payload["has_active_plan"],
        "is_admin": payload["is_admin"],
        "is_trial": payload["is_trial"],
        "can_manage_proxies": payload["can_manage_proxies"],
        "plan_expires_at": payload["plan_expires_at"],
        "trial_used_seconds": payload["trial_used_seconds"],
        "trial_limit_seconds": payload["trial_limit_seconds"],
        "trial_remaining_seconds": payload["trial_remaining_seconds"],
        "trial_exhausted": payload["trial_exhausted"],
        "registration_ip": user.registration_ip or user.registration_ip_plain,
        "last_ip": user.last_ip,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "has_session": bool(user.token),
    }


class GrantPlanBody(BaseModel):
    user_id: int
    plan_id: Literal[
        "premium-1-week",
        "premium-1-month",
        "premium-lifetime",
        "premium-custom",
    ] = "premium-1-month"
    # Any positive day count (custom grants, or override of preset plans).
    duration_days: int | None = Field(default=None, ge=1, le=36500)


class SetRankBody(BaseModel):
    user_id: int
    rank: str = Field(min_length=1, max_length=64)


class ResetTrialBody(BaseModel):
    user_id: int


class StopSniperBody(BaseModel):
    user_token: str = Field(min_length=8, max_length=128)
    platform: str = Field(min_length=2, max_length=32)


class CleanupSnipersBody(BaseModel):
    mode: Literal["orphans", "unauthorized", "all"] = "unauthorized"


@router.get("/overview")
async def admin_overview(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_admin(user)

    total_users = int((await db.execute(select(func.count()).select_from(User))).scalar_one())
    now = utc_now().replace(tzinfo=None)
    active_paid = int(
        (
            await db.execute(
                select(func.count()).select_from(User).where(User.plan_expires_at > now)
            )
        ).scalar_one()
    )
    trial_users = int(
        (
            await db.execute(
                select(func.count())
                .select_from(User)
                .where(User.rank.ilike("%trial%"), ~User.rank.ilike("%expired%"))
            )
        ).scalar_one()
    )
    pending_orders = int(
        (
            await db.execute(
                select(func.count())
                .select_from(PaymentOrder)
                .where(PaymentOrder.status.in_(("pending_review", "awaiting_payment", "pending_confirmations")))
            )
        ).scalar_one()
    )

    live = await _scan_live_snipers(request, db, active_only=True)
    # Resolve owner-token admins to usernames when present in DB.
    admin_labels = set(ADMIN_USERNAMES)
    token_result = await db.execute(select(User).where(User.token.in_(list(_owner_tokens()))))
    for u in token_result.scalars().all():
        if u.username:
            admin_labels.add(u.username.lower())
    return {
        "total_users": total_users,
        "active_paid": active_paid,
        "trial_users": trial_users,
        "pending_orders": pending_orders,
        "live_snipers": len(live),
        "admins": sorted(admin_labels),
    }


@router.get("/users")
async def admin_list_users(
    q: str | None = None,
    rank: str | None = None,
    plan: Literal["all", "paid", "trial", "expired", "admin"] | None = "all",
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_admin(user)

    query = select(User)
    count_query = select(func.count()).select_from(User)

    filters = []
    if q and q.strip():
        term = f"%{q.strip().lower()}%"
        ip_term = f"%{q.strip()}%"
        filters.append(
            or_(
                func.lower(User.username).like(term),
                User.registration_ip.like(ip_term),
                User.last_ip.like(ip_term),
                User.registration_ip_plain.like(ip_term),
            )
        )
    if rank and rank.strip():
        filters.append(User.rank.ilike(f"%{rank.strip()}%"))

    now = utc_now().replace(tzinfo=None)
    plan_filter = plan or "all"
    if plan_filter == "paid":
        filters.append(User.plan_expires_at > now)
    elif plan_filter == "trial":
        filters.append(User.rank.ilike("%trial%"))
        filters.append(~User.rank.ilike("%expired%"))
    elif plan_filter == "expired":
        filters.append(
            or_(
                User.rank.ilike("%expired%"),
                (User.plan_expires_at.is_not(None)) & (User.plan_expires_at <= now),
            )
        )
    elif plan_filter == "admin":
        filters.append(func.lower(User.username).in_(list(ADMIN_USERNAMES)))

    for f in filters:
        query = query.where(f)
        count_query = count_query.where(f)

    total = int((await db.execute(count_query)).scalar_one())
    result = await db.execute(query.order_by(User.id.desc()).offset(offset).limit(limit))
    users = result.scalars().all()
    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "users": [_user_row(u) for u in users],
    }


@router.get("/users/{user_id}")
async def admin_get_user(
    user_id: int,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Full account dossier for admin profile page (token, IPs, proxies, live jobs…)."""
    _require_admin(user)
    target = await db.get(User, user_id)
    if not target:
        raise HTTPException(404, "User not found")

    payload = plan_payload(target)
    can_manage = user_can_manage_proxies(target)
    token = (target.token or "").strip() or None

    proxies: list[str] = []
    settings_raw: dict = {}
    names_count = 0
    if token:
        proxies = await asyncio.to_thread(read_proxies, token)
        settings_raw = await asyncio.to_thread(read_settings, token)
        names_count = await asyncio.to_thread(count_names, token)

    using_trial_proxies = bool(payload.get("is_trial")) and not can_manage
    trial_proxy_count = len(get_trial_proxies()) if using_trial_proxies else 0

    orders_result = await db.execute(
        select(PaymentOrder)
        .where(PaymentOrder.user_id == user_id)
        .order_by(PaymentOrder.id.desc())
        .limit(30)
    )
    orders = orders_result.scalars().all()

    jobs_result = await db.execute(
        select(SniperJob)
        .where(SniperJob.user_id == user_id)
        .order_by(SniperJob.created_at.desc())
        .limit(25)
    )
    jobs = jobs_result.scalars().all()

    hits_result = await db.execute(
        select(SniperHit)
        .where(SniperHit.user_id == user_id)
        .order_by(SniperHit.id.desc())
        .limit(40)
    )
    hits = hits_result.scalars().all()

    logs_result = await db.execute(
        select(AdminAuditLog)
        .where(AdminAuditLog.target_user_id == user_id)
        .order_by(AdminAuditLog.id.desc())
        .limit(30)
    )
    audit_logs = logs_result.scalars().all()

    live_all = await _scan_live_snipers(request, db, active_only=False)
    live = [
        s
        for s in live_all
        if s.get("user_id") == user_id
        or (token and s.get("user_token") == token)
    ]
    live_active = [
        s for s in live if (s.get("state") or "").lower() in ("running", "queued")
    ]

    merged_settings = merge_settings(settings_raw) if settings_raw or token else {}

    return {
        "user": {
            **_user_row(target),
            "token": token,
            "token_prefix": token[:12] if token else None,
            "can_manage_proxies": can_manage,
            "using_trial_proxies": using_trial_proxies,
            "trial_proxy_count": trial_proxy_count,
            "names_count": names_count,
            "proxy_count": len(proxies),
        },
        "proxies": proxies,
        "settings": {
            "webhook_url": merged_settings.get("webhook_url") or "",
            "webhook_mode": merged_settings.get("webhook_mode") or "",
            "webhook_user_id": merged_settings.get("webhook_user_id") or "",
            "webhook_bot_username": merged_settings.get("webhook_bot_username") or "",
            "webhook_message_template": merged_settings.get("webhook_message_template")
            or "",
            "webhook_embed_enabled": bool(merged_settings.get("webhook_embed_enabled")),
        },
        "live_snipers": live_active,
        "all_sniper_sessions": live,
        "orders": [
            {
                "id": o.id,
                "plan_id": o.plan_id,
                "method": o.method,
                "status": o.status,
                "amount_usd": str(o.amount_usd) if o.amount_usd is not None else None,
                "currency": o.currency,
                "tx_hash": o.tx_hash,
                "sender_wallet": getattr(o, "sender_wallet", None),
                "note": getattr(o, "note", None),
                "created_at": o.created_at.isoformat() if o.created_at else None,
            }
            for o in orders
        ],
        "recent_jobs": [
            {
                "id": j.id,
                "platform": j.platform,
                "status": j.status,
                "workers": j.workers,
                "proxy": (j.proxy or "")[:200] or None,
                "webhook_url": j.webhook_url,
                "targets_count": len(j.targets) if isinstance(j.targets, list) else None,
                "stats": j.stats if isinstance(j.stats, dict) else None,
                "created_at": j.created_at.isoformat() if j.created_at else None,
                "updated_at": j.updated_at.isoformat() if j.updated_at else None,
            }
            for j in jobs
        ],
        "recent_hits": [
            {
                "id": h.id,
                "job_id": h.job_id,
                "platform": h.platform,
                "target": h.target,
                "status": h.status,
                "created_at": h.created_at.isoformat() if h.created_at else None,
            }
            for h in hits
        ],
        "audit_logs": [audit_row(r) for r in audit_logs],
    }


@router.post("/users/grant-plan")
async def admin_grant_plan(
    body: GrantPlanBody,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_admin(user)
    target = await db.get(User, body.user_id)
    if not target:
        raise HTTPException(404, "User not found")
    if is_admin(target):
        raise HTTPException(400, "Allowlisted admins already have full access")

    plan = GRANTABLE_PLANS[body.plan_id]
    duration = body.duration_days if body.duration_days is not None else plan["duration_days"]
    if body.plan_id == "premium-custom" and duration is None:
        raise HTTPException(400, "duration_days is required for custom premium grants")
    if body.plan_id == "premium-lifetime":
        duration = None
    await activate_plan(db, target, rank=plan["rank"], duration_days=duration)
    if duration is None:
        granted = "Lifetime"
    else:
        granted = f"{duration}-Day Premium"
    await record_admin_action(
        db,
        actor=user,
        action="grant_plan",
        target_user_id=target.id,
        target_username=target.username,
        detail=f"Granted {granted}",
        meta={"plan_id": body.plan_id, "duration_days": duration, "granted": granted},
        actor_ip=client_ip(request),
    )
    return {"ok": True, "user": _user_row(target), "granted": granted}


@router.post("/users/set-rank")
async def admin_set_rank(
    body: SetRankBody,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_admin(user)
    target = await db.get(User, body.user_id)
    if not target:
        raise HTTPException(404, "User not found")

    rank = body.rank.strip()
    if not rank:
        raise HTTPException(400, "Rank required")
    if rank.lower() == "admin" and not is_admin(target):
        raise HTTPException(
            400,
            f"Only allowlisted owners may be Admin ({', '.join(sorted(ADMIN_USERNAMES))} + owner tokens)",
        )
    if is_admin(target) and rank.lower() != "admin":
        raise HTTPException(400, "Cannot demote allowlisted admin accounts")

    prev = target.rank
    target.rank = rank
    if rank.lower() == "admin":
        target.plan_expires_at = None
    await record_admin_action(
        db,
        actor=user,
        action="set_rank",
        target_user_id=target.id,
        target_username=target.username,
        detail=f"Rank {prev or '—'} → {rank}",
        meta={"from": prev, "to": rank},
        actor_ip=client_ip(request),
        commit=False,
    )
    await db.commit()
    await db.refresh(target)
    return {"ok": True, "user": _user_row(target)}


@router.post("/users/reset-trial")
async def admin_reset_trial(
    body: ResetTrialBody,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_admin(user)
    target = await db.get(User, body.user_id)
    if not target:
        raise HTTPException(404, "User not found")
    if is_admin(target):
        raise HTTPException(400, "Cannot reset trial on admin accounts")

    target.rank = "Free Trial"
    target.trial_used_seconds = 0
    target.plan_expires_at = None
    await record_admin_action(
        db,
        actor=user,
        action="reset_trial",
        target_user_id=target.id,
        target_username=target.username,
        detail="Reset Free Trial to 5 minutes",
        actor_ip=client_ip(request),
        commit=False,
    )
    await db.commit()
    await db.refresh(target)
    return {"ok": True, "user": _user_row(target)}


@router.post("/trials/reset-all")
async def admin_reset_all_trials(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Give every trial account a fresh 5 minutes and clear stuck sniper sessions."""
    _require_admin(user)
    from scripts.reset_all_trials import reset_all_trials

    stats = await reset_all_trials(clear_sessions=True)
    await record_admin_action(
        db,
        actor=user,
        action="reset_all_trials",
        detail="Reset all Free Trial accounts",
        meta=dict(stats) if isinstance(stats, dict) else {"stats": stats},
        actor_ip=client_ip(request),
    )
    return {"ok": True, **stats}


@router.post("/users/clear-registration-ip")
async def admin_clear_registration_ip(
    body: ResetTrialBody,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Support: release an IP so someone else on the same network can sign up."""
    _require_admin(user)
    target = await db.get(User, body.user_id)
    if not target:
        raise HTTPException(404, "User not found")
    if is_admin(target):
        raise HTTPException(400, "Cannot clear IP on admin accounts")

    prev = target.registration_ip or target.registration_ip_plain
    target.registration_ip = None
    target.registration_ip_plain = None
    await record_admin_action(
        db,
        actor=user,
        action="clear_registration_ip",
        target_user_id=target.id,
        target_username=target.username,
        detail=f"Cleared registration IP {prev or '—'}",
        meta={"cleared_ip": prev},
        actor_ip=client_ip(request),
        commit=False,
    )
    await db.commit()
    await db.refresh(target)
    return {"ok": True, "cleared_ip": prev, "user": _user_row(target)}


@router.post("/users/expire")
async def admin_expire_user(
    body: ResetTrialBody,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_admin(user)
    target = await db.get(User, body.user_id)
    if not target:
        raise HTTPException(404, "User not found")
    if is_admin(target):
        raise HTTPException(400, "Cannot expire admin accounts")

    target.rank = "Free Trial Expired"
    target.trial_used_seconds = 300
    target.plan_expires_at = utc_now().replace(tzinfo=None)
    await record_admin_action(
        db,
        actor=user,
        action="expire_user",
        target_user_id=target.id,
        target_username=target.username,
        detail="Expired plan / trial",
        actor_ip=client_ip(request),
        commit=False,
    )
    await db.commit()
    await db.refresh(target)

    # Immediately kill any live sessions for this account (stops proxy burn).
    stopped = 0
    if target.token:
        from services.sniper_cleanup import scan_status_keys

        for token, platform, data in await scan_status_keys(request.app.state.redis):
            if token != target.token:
                continue
            if (data.get("state") or "").lower() not in ("running", "queued"):
                continue
            await request_sniper_stop(request.app.state.redis, token, platform)
            stopped += 1

    return {"ok": True, "user": _user_row(target), "snipers_stopped": stopped}


@router.post("/users/{user_id}/proxies/clear")
async def admin_clear_user_proxies(
    user_id: int,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Wipe the client's saved custom proxy list (proxies.txt)."""
    _require_admin(user)
    target = await db.get(User, user_id)
    if not target:
        raise HTTPException(404, "User not found")
    token = (target.token or "").strip()
    if not token:
        raise HTTPException(400, "User has no session token / storage folder")

    before = await asyncio.to_thread(read_proxies, token)
    await asyncio.to_thread(write_proxies, token, [])
    await record_admin_action(
        db,
        actor=user,
        action="clear_proxies",
        target_user_id=target.id,
        target_username=target.username,
        detail=f"Cleared {len(before)} proxy line(s)",
        meta={"cleared": len(before)},
        actor_ip=client_ip(request),
    )
    return {"ok": True, "cleared": len(before), "proxies": []}


@router.delete("/users/{user_id}")
async def admin_delete_user(
    user_id: int,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Permanently delete a client account, its data, and stop any live snipers."""
    _require_admin(user)
    if user_id == user.id:
        raise HTTPException(400, "Cannot delete your own admin account")

    target = await db.get(User, user_id)
    if not target:
        raise HTTPException(404, "User not found")
    if is_admin(target):
        raise HTTPException(400, "Cannot delete admin accounts")

    username = target.username
    token = target.token
    stopped = 0

    if token:
        for sess_token, platform, data in await scan_status_keys(request.app.state.redis):
            if sess_token != token:
                continue
            if (data.get("state") or "").lower() not in ("running", "queued"):
                continue
            await request_sniper_stop(request.app.state.redis, token, platform)
            stopped += 1

    await record_admin_action(
        db,
        actor=user,
        action="delete_user",
        target_user_id=user_id,
        target_username=username,
        detail=f"Deleted account #{user_id}",
        meta={"snipers_stopped": stopped},
        actor_ip=client_ip(request),
        commit=False,
    )
    await db.execute(delete(SniperHit).where(SniperHit.user_id == user_id))
    await db.execute(delete(SniperJob).where(SniperJob.user_id == user_id))
    await db.execute(delete(PaymentOrder).where(PaymentOrder.user_id == user_id))
    await db.delete(target)
    await db.commit()

    if token:
        await request.app.state.redis.delete(f"sniper:trial:lock:{user_id}")
        data_path = user_dir(token)
        if data_path.is_dir():
            await asyncio.to_thread(shutil.rmtree, data_path, True)

    return {"ok": True, "deleted_user_id": user_id, "username": username, "snipers_stopped": stopped}


@router.get("/proxies")
async def admin_list_proxies(
    q: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List custom proxy lists uploaded by paid / lifetime clients."""
    _require_admin(user)

    query = select(User).where(User.token.is_not(None))

    if q and q.strip():
        term = f"%{q.strip().lower()}%"
        query = query.where(func.lower(User.username).like(term))

    result = await db.execute(query.order_by(User.id.desc()))
    users = result.scalars().all()

    entries: list[dict] = []
    for u in users:
        if not u.token:
            continue
        can_manage = user_can_manage_proxies(u)
        proxies = await asyncio.to_thread(read_proxies, u.token)
        if not can_manage and not proxies:
            continue
        entries.append(
            {
                "user_id": u.id,
                "username": u.username,
                "rank": u.rank,
                "has_active_plan": plan_payload(u)["has_active_plan"],
                "can_manage_proxies": can_manage,
                "proxy_count": len(proxies),
                "proxies": proxies,
            }
        )

    total = len(entries)
    page = entries[offset : offset + limit]
    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "clients": page,
    }


async def _scan_live_snipers(request: Request, db: AsyncSession, *, active_only: bool) -> list[dict]:
    parsed = await scan_status_keys(request.app.state.redis)
    token_to_user: dict[str, User] = {}
    tokens: set[str] = set()
    filtered: list[tuple[str, str, dict]] = []

    for token, platform, data in parsed:
        state = (data.get("state") or "idle").lower()
        if active_only and state not in ("running", "queued"):
            continue
        tokens.add(token)
        filtered.append((token, platform, data))

    if tokens:
        result = await db.execute(select(User).where(User.token.in_(list(tokens))))
        for u in result.scalars().all():
            if u.token:
                token_to_user[u.token] = u

    sessions: list[dict] = []
    for token, platform, data in filtered:
        owner = token_to_user.get(token)
        sessions.append(
            {
                "user_id": owner.id if owner else None,
                "username": owner.username if owner else None,
                "rank": owner.rank if owner else None,
                "last_ip": owner.last_ip if owner else None,
                "user_token": token,
                "token_prefix": token[:12],
                "orphan": owner is None,
                "unauthorized": owner is None
                or (not is_admin(owner) and not plan_payload(owner)["has_active_plan"]),
                "platform": platform or data.get("platform"),
                "state": data.get("state"),
                "progress_pct": data.get("progress_pct"),
                "checks_done": data.get("checks_done"),
                "total_names": data.get("total_names"),
                "checks_per_sec": data.get("checks_per_sec"),
                "available": data.get("available"),
                "occupied": data.get("occupied"),
                "errors": data.get("errors"),
                "rate_limits": data.get("rate_limits"),
                "elapsed_seconds": data.get("elapsed_seconds"),
                "current_target": data.get("current_target"),
                "vps_pool": data.get("vps_pool"),
                "node_id": data.get("node_id"),
                "started_at": data.get("started_at"),
                "captures": len(data.get("captures") or []),
                "trial_remaining_seconds": data.get("trial_remaining_seconds"),
            }
        )

    sessions.sort(key=lambda s: (-(s.get("checks_per_sec") or 0), s.get("username") or ""))
    return sessions


@router.get("/snipers")
async def admin_live_snipers(
    request: Request,
    active_only: bool = True,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_admin(user)
    sessions = await _scan_live_snipers(request, db, active_only=active_only)
    return {"count": len(sessions), "snipers": sessions}


@router.post("/snipers/stop")
async def admin_stop_sniper(
    body: StopSniperBody,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_admin(user)
    result = await request_sniper_stop(request.app.state.redis, body.user_token, body.platform)
    await record_admin_action(
        db,
        actor=user,
        action="stop_sniper",
        detail=f"Stopped {body.platform} sniper",
        meta={
            "platform": body.platform,
            "token_prefix": body.user_token[:12],
            **({k: result[k] for k in result} if isinstance(result, dict) else {}),
        },
        actor_ip=client_ip(request),
    )
    return {"ok": True, "platform": body.platform, **result}


@router.post("/snipers/cleanup")
async def admin_cleanup_snipers(
    body: CleanupSnipersBody,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Kill orphaned tokens and/or expired-trial / no-plan runners burning proxies."""
    _require_admin(user)
    result = await cleanup_live_snipers(request.app.state.redis, db, mode=body.mode)
    await record_admin_action(
        db,
        actor=user,
        action="cleanup_snipers",
        detail=f"Cleanup mode={body.mode}",
        meta={"mode": body.mode, **(result if isinstance(result, dict) else {})},
        actor_ip=client_ip(request),
    )
    return {"ok": True, **result}


@router.get("/logs")
async def admin_list_logs(
    q: str | None = None,
    action: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Read-only audit trail of admin panel actions — visible to every admin."""
    _require_admin(user)

    query = select(AdminAuditLog)
    count_query = select(func.count()).select_from(AdminAuditLog)

    if q and q.strip():
        term = f"%{q.strip().lower()}%"
        filt = or_(
            func.lower(AdminAuditLog.actor_username).like(term),
            func.lower(AdminAuditLog.target_username).like(term),
            func.lower(AdminAuditLog.detail).like(term),
            func.lower(AdminAuditLog.action).like(term),
        )
        query = query.where(filt)
        count_query = count_query.where(filt)

    if action and action.strip():
        filt = AdminAuditLog.action == action.strip()
        query = query.where(filt)
        count_query = count_query.where(filt)

    total = int((await db.execute(count_query)).scalar_one())
    result = await db.execute(
        query.order_by(AdminAuditLog.id.desc()).offset(offset).limit(limit)
    )
    rows = result.scalars().all()
    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "logs": [audit_row(r) for r in rows],
    }
