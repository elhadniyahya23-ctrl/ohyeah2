import pytest

from services.webhook import build_webhook_payload, is_allowed_webhook_url


def test_discord_webhook_url_validation():
    assert is_allowed_webhook_url("https://discord.com/api/webhooks/1/abc")
    assert is_allowed_webhook_url("https://discordapp.com/api/webhooks/1/abc")
    assert not is_allowed_webhook_url("https://example.com/hook")
    assert not is_allowed_webhook_url("http://169.254.169.254/")


def test_build_webhook_payload_rejects_non_discord_url():
    with pytest.raises(ValueError):
        build_webhook_payload(
            url="https://evil.example/hook",
            webhook_mode="everyone",
            webhook_user_id="",
            webhook_message_template="{platform} `{username}`",
            webhook_bot_username="Bot",
            webhook_avatar_url="",
            webhook_embed_enabled=False,
        )


def test_build_webhook_payload_embed():
    payload = build_webhook_payload(
        url="https://discord.com/api/webhooks/1/abc",
        webhook_mode="none",
        webhook_user_id="",
        webhook_message_template="Available: `{username}`",
        webhook_bot_username="Bot",
        webhook_avatar_url="",
        webhook_embed_enabled=True,
        webhook_embed_title="Hit",
        webhook_embed_description="PreviewUser is free",
        webhook_embed_color="#5865F2",
        webhook_embed_footer="",
        webhook_embed_footer_icon="",
        webhook_embed_thumbnail=False,
        webhook_embed_thumbnail_url="",
        webhook_embed_author_name="",
        webhook_embed_author_icon="",
    )
    assert "embeds" in payload
    assert payload["embeds"][0]["title"] == "Hit"
