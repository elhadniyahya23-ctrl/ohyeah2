import asyncio

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from database import User
from deps import get_current_user, user_storage_token
from services.trial_proxies import user_can_manage_proxies
from services.user_store import normalize_proxy_lines_detailed, read_proxies, write_proxies

router = APIRouter()


class ProxiesBody(BaseModel):
    proxies: list[str] = Field(default_factory=list)


@router.get("/proxies")
async def get_proxies(user: User = Depends(get_current_user)):
    if not user_can_manage_proxies(user):
        raise HTTPException(
            403,
            "Proxies unlock after you upgrade — Free Trial uses our shared proxies.",
        )
    token = user_storage_token(user)
    proxies = await asyncio.to_thread(read_proxies, token)
    return {"proxies": proxies, "count": len(proxies)}


@router.post("/proxies")
async def save_proxies(body: ProxiesBody, user: User = Depends(get_current_user)):
    if not user_can_manage_proxies(user):
        raise HTTPException(
            403,
            "Proxies unlock after you upgrade — Free Trial uses our shared proxies.",
        )
    token = user_storage_token(user)
    detailed = normalize_proxy_lines_detailed(body.proxies)
    proxies = detailed["proxies"]
    try:
        await asyncio.to_thread(write_proxies, token, proxies)
        stored = await asyncio.to_thread(read_proxies, token)
    except OSError as exc:
        raise HTTPException(500, f"Could not write proxies on server: {exc}") from exc
    return {
        "ok": True,
        "count": len(stored),
        "proxies": stored,
        "duplicates": int(detailed["duplicates"]),
        "invalid": int(detailed["invalid"]),
    }
