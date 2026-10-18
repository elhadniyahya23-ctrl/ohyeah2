from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from database import User, get_db
from deps import get_current_user, get_optional_user
from services.auth import (
    create_user,
    get_user_by_username,
    invalidate_session,
    plan_payload,
    update_login_metadata,
    user_has_active_plan,
    validate_username,
    verify_password,
)
from services.request_utils import client_ip
from services.signup_guard import client_ip_from_request

router = APIRouter()


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=32)
    password: str = Field(min_length=6, max_length=128)


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=32)
    password: str = Field(min_length=1, max_length=128)


class UserResponse(BaseModel):
    user_id: int
    username: str
    token: str
    rank: str | None
    plan_expires_at: str | None
    has_active_plan: bool
    is_admin: bool = False
    is_trial: bool = False
    can_manage_proxies: bool = False
    trial_used_seconds: int = 0
    trial_limit_seconds: int = 300
    trial_remaining_seconds: int | None = None
    trial_exhausted: bool = False


def to_user_response(user: User) -> UserResponse:
    plan = plan_payload(user)
    return UserResponse(
        user_id=user.id,
        username=user.username,
        token=user.token or "",
        rank=plan["rank"] if not plan["is_admin"] else "Admin",
        plan_expires_at=plan["plan_expires_at"],
        has_active_plan=plan["has_active_plan"],
        is_admin=plan["is_admin"],
        is_trial=plan["is_trial"],
        can_manage_proxies=plan["can_manage_proxies"],
        trial_used_seconds=plan["trial_used_seconds"],
        trial_limit_seconds=plan["trial_limit_seconds"],
        trial_remaining_seconds=plan["trial_remaining_seconds"],
        trial_exhausted=plan["trial_exhausted"],
    )


@router.post("/register", response_model=UserResponse)
async def register(body: RegisterRequest, request: Request, db: AsyncSession = Depends(get_db)):
    username = body.username.strip()
    try:
        validate_username(username)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e

    existing = await get_user_by_username(db, username)
    if existing:
        raise HTTPException(409, "Username already taken")

    ip, _ = client_ip_from_request(request)
    user = await create_user(db, username, body.password, ip=ip)
    return to_user_response(user)


@router.post("/login", response_model=UserResponse)
async def login(body: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)):
    username = body.username.strip()
    user = await get_user_by_username(db, username)
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "Invalid username or password")

    await update_login_metadata(db, user, client_ip(request), password=body.password)
    return to_user_response(user)


@router.get("/me", response_model=UserResponse)
async def me(user: User = Depends(get_current_user)):
    return to_user_response(user)


@router.post("/logout")
async def logout(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await invalidate_session(db, user)
    return {"ok": True}
