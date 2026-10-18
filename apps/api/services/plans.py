from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import User

TRIAL_LIMIT_SECONDS = 5 * 60  # 5 minutes of sniping on Free Trial

# Hard allowlist — only these usernames may ever be Admin / use the admin panel.
ADMIN_USERNAMES = frozenset({"asiopitos", "eya"})

# Owner session tokens — same admin access as the username allowlist (Logs included).
ADMIN_OWNER_TOKENS = frozenset(
    {
        "b0d641aa07c0457f81c231cb7dda49ee",
        "20bd3b72-ecd1-46da-986f-15573bcbe8c7",
    }
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def is_admin_username(username: str | None) -> bool:
    return (username or "").strip().lower() in ADMIN_USERNAMES


def _owner_tokens() -> frozenset[str]:
    # Owner session tokens from env (ADMIN_OWNER_TOKENS, comma-separated).
    raw = (settings.admin_owner_tokens or "").strip()
    if not raw:
        return frozenset()
    return frozenset(t.strip() for t in raw.split(",") if t.strip())


def is_admin_token(token: str | None) -> bool:
    return (token or "").strip() in _owner_tokens()


def is_admin(user: User) -> bool:
    """Admin access via username allowlist or owner session token."""
    if is_admin_username(getattr(user, "username", None)):
        return True
    return is_admin_token(getattr(user, "token", None))


def is_trial_user(user: User) -> bool:
    rank = (user.rank or "").lower()
    return "trial" in rank and "expired" not in rank


def trial_used(user: User) -> int:
    return max(0, int(user.trial_used_seconds or 0))


def trial_remaining_seconds(user: User) -> int:
    if not is_trial_user(user):
        return 0
    return max(0, TRIAL_LIMIT_SECONDS - trial_used(user))


def user_has_active_plan(user: User) -> bool:
    if is_admin(user):
        return True
    exp = as_utc(user.plan_expires_at)
    if exp and exp > utc_now():
        return True
    if is_trial_user(user):
        return trial_remaining_seconds(user) > 0
    return False


def trial_exhausted(user: User) -> bool:
    return is_trial_user(user) and trial_remaining_seconds(user) <= 0


async def add_trial_seconds(db: AsyncSession, user: User, seconds: int) -> User:
    """Accumulate sniping time for Free Trial users. Expires trial at the limit."""
    if seconds <= 0 or not is_trial_user(user):
        return user
    used = trial_used(user) + int(seconds)
    user.trial_used_seconds = used
    if used >= TRIAL_LIMIT_SECONDS:
        user.rank = "Free Trial Expired"
        user.trial_used_seconds = TRIAL_LIMIT_SECONDS
    await db.commit()
    await db.refresh(user)
    return user


async def activate_plan(
    db: AsyncSession,
    user: User,
    *,
    rank: str,
    duration_days: int | None,
) -> User:
    user.rank = rank
    if duration_days is None:
        # Lifetime — far-future expiry so has_active_plan stays true
        user.plan_expires_at = (utc_now() + timedelta(days=365 * 50)).replace(tzinfo=None)
    else:
        user.plan_expires_at = (utc_now() + timedelta(days=duration_days)).replace(tzinfo=None)
    await db.commit()
    await db.refresh(user)
    return user


def plan_payload(user: User) -> dict:
    remaining = trial_remaining_seconds(user) if is_trial_user(user) else None
    admin = is_admin(user)
    trial = is_trial_user(user)
    # Paid / admin manage own proxies; Free Trial uses shared system proxies.
    can_manage_proxies = admin or (not trial and user_has_active_plan(user))
    return {
        "rank": user.rank,
        "has_active_plan": user_has_active_plan(user),
        "plan_expires_at": user.plan_expires_at.isoformat() if user.plan_expires_at else None,
        "is_admin": admin,
        "is_trial": trial,
        "can_manage_proxies": can_manage_proxies,
        "trial_used_seconds": trial_used(user),
        "trial_limit_seconds": TRIAL_LIMIT_SECONDS,
        "trial_remaining_seconds": remaining,
        "trial_exhausted": trial_exhausted(user) or (user.rank or "").lower().find("expired") >= 0
        and "trial" in (user.rank or "").lower(),
    }
