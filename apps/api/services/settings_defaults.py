DEFAULT_SETTINGS: dict = {
    "webhook_url": "",
    "webhook_mode": "everyone",
    "webhook_user_id": "",
    "webhook_message_template": "{platform} username available: `{username}`",
    "webhook_bot_username": "User Sniper",
    "webhook_avatar_url": "",
    "webhook_embed_enabled": False,
    "webhook_embed_title": "",
    "webhook_embed_description": "",
    "webhook_embed_color": "#5865F2",
    "webhook_embed_footer": "",
    "webhook_embed_footer_icon": "",
    "webhook_embed_thumbnail": False,
    "webhook_embed_thumbnail_url": "",
    "webhook_embed_author_name": "",
    "webhook_embed_author_icon": "",
}


def merge_settings(stored: dict) -> dict:
    merged = dict(DEFAULT_SETTINGS)
    merged.update(stored)
    return merged


def render_ping(mode: str, user_id: str) -> str:
    if mode == "everyone":
        return "@everyone"
    if mode == "user" and user_id.strip():
        return f"<@{user_id.strip()}>"
    return ""


def apply_template(template: str, *, username: str, platform: str, ping: str) -> str:
    text = template or DEFAULT_SETTINGS["webhook_message_template"]
    return (
        text.replace("{username}", username)
        .replace("{platform}", platform)
        .replace("{platform_lower}", platform.lower())
        .replace("{ping}", ping)
    )
