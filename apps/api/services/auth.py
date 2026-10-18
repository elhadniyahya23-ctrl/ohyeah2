import re
import uuid
from datetime import datetime, timezone

import bcrypt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from werkzeug.security import check_password_hash

from database import User
from services.plans import (  # noqa: E402
    ADMIN_USERNAMES,
    TRIAL_LIMIT_SECONDS,
    add_trial_seconds,
    is_admin,
    is_admin_username,
    plan_payload,
    trial_exhausted,
    trial_remaining_seconds,
    user_has_active_plan,
)

USERNAME_RE = re.compile(r"^[a-zA-Z0-9_]{3,32}$")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def verify_password(plain: str, hashed: str) -> bool:
    if not plain or not hashed:
        return False
    try:
        # Legacy accounts from the previous site (Werkzeug scrypt/pbkdf2).
        if hashed.startswith(("scrypt:", "pbkdf2:", "argon2:")):
            return check_password_hash(hashed, plain)
        # Standard bcrypt hashes.
        if hashed.startswith(("$2a$", "$2b$", "$2y$")):
            return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
        # Last resort for any other werkzeug-compatible format.
        return check_password_hash(hashed, plain)
    except (ValueError, TypeError):
        return False


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def is_legacy_password_hash(hashed: str) -> bool:
    return hashed.startswith(("scrypt:", "pbkdf2:", "argon2:"))


async def get_user_by_username(db: AsyncSession, username: str) -> User | None:
    result = await db.execute(select(User).where(User.username == username))
    return result.scalar_one_or_none()


async def get_user_by_token(db: AsyncSession, token: str) -> User | None:
    result = await db.execute(select(User).where(User.token == token))
    return result.scalar_one_or_none()


async def create_user(db: AsyncSession, username: str, password: str, ip: str | None = None) -> User:
    now = utc_now().replace(tzinfo=None)
    admin = is_admin_username(username)
    user = User(
        username=username,
        password_hash=hash_password(password),
        token=str(uuid.uuid4()),
        rank="Admin" if admin else "Free Trial",
        created_at=now,
        registration_ip=ip,
        registration_ip_plain=ip,
        last_ip=ip,
        trial_used_seconds=0,
        plan_expires_at=None,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


def validate_username(username: str) -> None:
    if not USERNAME_RE.match(username):
        raise ValueError("Username must be 3-32 characters: letters, numbers, underscores only")


async def update_login_metadata(
    db: AsyncSession, user: User, ip: str | None, *, password: str | None = None
) -> None:
    user.last_ip = ip
    if password and is_legacy_password_hash(user.password_hash):
        user.password_hash = hash_password(password)
    # Keep allowlisted admins marked Admin in DB; strip Admin from everyone else.
    if is_admin_username(user.username):
        if (user.rank or "").lower() != "admin":
            user.rank = "Admin"
            user.plan_expires_at = None
    elif (user.rank or "").lower() == "admin":
        user.rank = "Free Trial"
    await db.commit()


async def invalidate_session(db: AsyncSession, user: User) -> None:
    user.token = str(uuid.uuid4())
    await db.commit()


async def update_user_password(db: AsyncSession, username: str, password: str) -> User:
    user = await get_user_by_username(db, username)
    if user is None:
        raise ValueError(f"User not found: {username}")
    user.password_hash = hash_password(password)
    await db.commit()
    await db.refresh(user)
    return user


async def update_user_rank(db: AsyncSession, username: str, rank: str) -> User:
    user = await get_user_by_username(db, username)
    if user is None:
        raise ValueError(f"User not found: {username}")
    if rank.lower() == "admin" and not is_admin_username(username):
        raise ValueError(
            f"Refused: only {', '.join(sorted(ADMIN_USERNAMES))} may be Admin"
        )
    user.rank = rank
    if rank.lower() == "admin":
        user.plan_expires_at = None
    await db.commit()
    await db.refresh(user)
    return user
