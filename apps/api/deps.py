from fastapi import Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from database import User, get_db
from services.auth import get_user_by_token


def user_storage_token(user: User) -> str:
    token = (user.token or "").strip()
    if not token:
        raise HTTPException(500, "Account session is invalid. Please log in again.")
    return token


async def get_current_user(
    x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    db: AsyncSession = Depends(get_db),
) -> User:
    if not x_session_token:
        raise HTTPException(401, "Missing session token")
    user = await get_user_by_token(db, x_session_token)
    if not user:
        raise HTTPException(401, "Invalid session token")
    return user


async def get_optional_user(
    x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    db: AsyncSession = Depends(get_db),
) -> User | None:
    if not x_session_token:
        return None
    return await get_user_by_token(db, x_session_token)
