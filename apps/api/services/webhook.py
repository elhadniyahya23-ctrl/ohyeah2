from __future__ import annotations

import re
from typing import Any

from services.settings_defaults import DEFAULT_SETTINGS, apply_template, render_ping

DISCORD_WEBHOOK_PREFIXES = (
    "https://discord.com/api/webhooks/",
    "https://discordapp.com/api/webhooks/",
)

HEX_COLOR_RE = re.compile(r"^#?[0-9a-fA-F]{6}$")


def is_allowed_webhook_url(url: str) -> bool:
    normalized = url.strip().lower()
    return any(normalized.startswith(prefix) for prefix in DISCORD_WEBHOOK_PREFIXES)


def parse_embed_color(raw: str) -> int:
    value = (raw or DEFAULT_SETTINGS["webhook_embed_color"]).strip().lstrip("#")
    if not HEX_COLOR_RE.match(f"#{value}"):
        return int("5865F2", 16)
    return int(value, 16)


def build_webhook_payload(
    *,
    url: str,
    webhook_mode: str,
    webhook_user_id: str,
    webhook_message_template: str,
    webhook_bot_username: str,
    webhook_avatar_url: str,
    webhook_embed_enabled: bool,
    webhook_embed_title: str = "",
    webhook_embed_description: str = "",
    webhook_embed_color: str = DEFAULT_SETTINGS["webhook_embed_color"],
    webhook_embed_footer: str = "",
    webhook_embed_footer_icon: str = "",
    webhook_embed_thumbnail: bool = False,
    webhook_embed_thumbnail_url: str = "",
    webhook_embed_author_name: str = "",
    webhook_embed_author_icon: str = "",
    preview_platform: str = "discord",
    preview_username: str = "PreviewUser",
) -> dict[str, Any]:
    if not is_allowed_webhook_url(url):
        raise ValueError("Webhook URL must be a Discord webhook URL")

    ping = render_ping(webhook_mode, webhook_user_id)
    content = apply_template(
        webhook_message_template,
        username=preview_username,
        platform=preview_platform,
        ping=ping,
    )
    if ping and ping not in content:
        content = f"{ping} {content}".strip()

    payload: dict[str, Any] = {"content": content[:2000]}
    if webhook_bot_username.strip():
        payload["username"] = webhook_bot_username.strip()[:80]
    if webhook_avatar_url.strip():
        payload["avatar_url"] = webhook_avatar_url.strip()

    if webhook_embed_enabled:
        embed: dict[str, Any] = {"color": parse_embed_color(webhook_embed_color)}
        if webhook_embed_title.strip():
            embed["title"] = webhook_embed_title.strip()[:256]
        if webhook_embed_description.strip():
            embed["description"] = webhook_embed_description.strip()[:4096]
        else:
            embed["description"] = content[:4096]
        if webhook_embed_footer.strip():
            footer: dict[str, str] = {"text": webhook_embed_footer.strip()[:2048]}
            if webhook_embed_footer_icon.strip():
                footer["icon_url"] = webhook_embed_footer_icon.strip()
            embed["footer"] = footer
        if webhook_embed_thumbnail and webhook_embed_thumbnail_url.strip():
            embed["thumbnail"] = {"url": webhook_embed_thumbnail_url.strip()}
        if webhook_embed_author_name.strip():
            author: dict[str, str] = {"name": webhook_embed_author_name.strip()[:256]}
            if webhook_embed_author_icon.strip():
                author["icon_url"] = webhook_embed_author_icon.strip()
            embed["author"] = author
        payload["embeds"] = [embed]
        if not payload["content"]:
            payload.pop("content", None)

    return payload
