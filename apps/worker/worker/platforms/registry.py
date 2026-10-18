from __future__ import annotations

from worker.platforms.base import PlatformChecker
from worker.platforms.discord import DiscordChecker
from worker.platforms.epic import EpicChecker
from worker.platforms.github import GitHubChecker
from worker.platforms.guns import GunsChecker
from worker.platforms.instagram import InstagramChecker
from worker.platforms.minecraft import MinecraftChecker
from worker.platforms.reddit import RedditChecker
from worker.platforms.roblox import RobloxChecker
from worker.platforms.snapchat import SnapchatChecker
from worker.platforms.steam import SteamChecker
from worker.platforms.telegram import TelegramChecker
from worker.platforms.tiktok import TikTokChecker
from worker.platforms.twitter import TwitterChecker
from worker.platforms.ubisoft import UbisoftChecker
from worker.platforms.whatsapp import WhatsAppChecker
from worker.platforms.youtube import YouTubeChecker

ENDPOINT_CHECKERS: dict[str, PlatformChecker] = {
    "discord": DiscordChecker(),
    "roblox": RobloxChecker(),
    "minecraft": MinecraftChecker(),
    "github": GitHubChecker(),
    "reddit": RedditChecker(),
    "steam": SteamChecker(),
    "telegram": TelegramChecker(),
    "whatsapp": WhatsAppChecker(),
    "instagram": InstagramChecker(),
    "tiktok": TikTokChecker(),
    "twitter": TwitterChecker(),
    "snapchat": SnapchatChecker(),
    "youtube": YouTubeChecker(),
    "guns": GunsChecker(),
    "epic": EpicChecker(),
    "ubisoft": UbisoftChecker(),
}


def get_checker(platform: str) -> PlatformChecker | None:
    return ENDPOINT_CHECKERS.get(platform)


def all_platforms() -> list[str]:
    return list(ENDPOINT_CHECKERS.keys())
