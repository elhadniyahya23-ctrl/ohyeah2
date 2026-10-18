import asyncio

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from database import User
from deps import get_current_user, user_storage_token
from services.settings_defaults import DEFAULT_SETTINGS, merge_settings
from services.user_store import read_settings, write_settings
from services.webhook import build_webhook_payload, is_allowed_webhook_url

router = APIRouter()

ALLOWED_WEBHOOK_MODES = {"everyone", "user", "none"}


class SettingsUpdate(BaseModel):
    webhook_url: str | None = None
    webhook_mode: str | None = None
    webhook_user_id: str | None = None
    webhook_message_template: str | None = None
    webhook_bot_username: str | None = None
    webhook_avatar_url: str | None = None
    webhook_embed_enabled: bool | None = None
    webhook_embed_title: str | None = None
    webhook_embed_description: str | None = None
    webhook_embed_color: str | None = None
    webhook_embed_footer: str | None = None
    webhook_embed_footer_icon: str | None = None
    webhook_embed_thumbnail: bool | None = None
    webhook_embed_thumbnail_url: str | None = None
    webhook_embed_author_name: str | None = None
    webhook_embed_author_icon: str | None = None


class WebhookTestBody(BaseModel):
    url: str = Field(min_length=8)
    webhook_mode: str = "everyone"
    webhook_user_id: str = ""
    webhook_message_template: str = DEFAULT_SETTINGS["webhook_message_template"]
    webhook_bot_username: str = DEFAULT_SETTINGS["webhook_bot_username"]
    webhook_avatar_url: str = ""
    webhook_embed_enabled: bool = False
    webhook_embed_title: str = ""
    webhook_embed_description: str = ""
    webhook_embed_color: str = DEFAULT_SETTINGS["webhook_embed_color"]
    webhook_embed_footer: str = ""
    webhook_embed_footer_icon: str = ""
    webhook_embed_thumbnail: bool = False
    webhook_embed_thumbnail_url: str = ""
    webhook_embed_author_name: str = ""
    webhook_embed_author_icon: str = ""
    preview_platform: str = "discord"


@router.get("/settings")
async def get_settings(user: User = Depends(get_current_user)):
    token = user_storage_token(user)
    stored = await asyncio.to_thread(read_settings, token)
    return merge_settings(stored)


@router.post("/settings")
async def save_settings(body: SettingsUpdate, user: User = Depends(get_current_user)):
    token = user_storage_token(user)
    stored = await asyncio.to_thread(read_settings, token)
    current = merge_settings(stored)
    updates = body.model_dump(exclude_unset=True)

    mode = updates.get("webhook_mode")
    if mode is not None and mode not in ALLOWED_WEBHOOK_MODES:
        raise HTTPException(400, "Invalid webhook mode")

    url = updates.get("webhook_url")
    if url is not None and url.strip() and not is_allowed_webhook_url(url):
        raise HTTPException(400, "Webhook URL must be a Discord webhook URL")

    current.update(updates)
    await asyncio.to_thread(write_settings, token, current)
    return {"success": True, "settings": current}


@router.post("/settings/test-webhook")
async def test_webhook(body: WebhookTestBody, _user: User = Depends(get_current_user)):
    from config import settings

    if settings.local_safe_mode:
        raise HTTPException(
            403,
            "Local safe mode is enabled: outbound webhook tests are disabled on localhost.",
        )

    url = body.url.strip()
    if body.webhook_mode not in ALLOWED_WEBHOOK_MODES:
        raise HTTPException(400, "Invalid webhook mode")

    try:
        payload = build_webhook_payload(
            url=url,
            webhook_mode=body.webhook_mode,
            webhook_user_id=body.webhook_user_id,
            webhook_message_template=body.webhook_message_template,
            webhook_bot_username=body.webhook_bot_username,
            webhook_avatar_url=body.webhook_avatar_url,
            webhook_embed_enabled=body.webhook_embed_enabled,
            webhook_embed_title=body.webhook_embed_title,
            webhook_embed_description=body.webhook_embed_description,
            webhook_embed_color=body.webhook_embed_color,
            webhook_embed_footer=body.webhook_embed_footer,
            webhook_embed_footer_icon=body.webhook_embed_footer_icon,
            webhook_embed_thumbnail=body.webhook_embed_thumbnail,
            webhook_embed_thumbnail_url=body.webhook_embed_thumbnail_url,
            webhook_embed_author_name=body.webhook_embed_author_name,
            webhook_embed_author_icon=body.webhook_embed_author_icon,
            preview_platform=body.preview_platform,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            res = await client.post(url, json=payload)
    except httpx.RequestError as exc:
        raise HTTPException(502, "Could not reach Discord webhook endpoint") from exc

    if res.status_code >= 400:
        raise HTTPException(400, f"Discord rejected the webhook ({res.status_code})")
    return {"success": True}
