from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Sync TurboEngine (turbo_engine.py) calls check(target, proxy_url) via requests.
# sniper/discord.py is the aiohttp variant for engine.py — NOT compatible here.
from sniper.discord_checker import DiscordChecker
from sniper.checkers.instagram_checker import InstagramChecker
from sniper.checkers.minecraft_checker import MinecraftChecker
from sniper.checkers.roblox_checker import RobloxChecker
from sniper.guns import GunsChecker
from sniper.tiktok import TikTokChecker

# Live platforms — everything else is coming soon.
TURBO_PLATFORMS = frozenset(
    {
        "discord",
        "instagram",
        "roblox",
        "minecraft",
        "tiktok",
        "guns",
    }
)

COMING_SOON_PLATFORMS = frozenset(
    {
        "telegram",
        "whatsapp",
        "snapchat",
        "youtube",
        "epic",
        "twitter",
        "steam",
        "ubisoft",
        "github",
        "reddit",
    }
)

# Lower Discord parallelism — 6–12 was over-hitting 429 (~1:1 RL:valid).
WORKERS_PER_PROXY = 3
DISCORD_MAX_WORKERS = 6


@dataclass(frozen=True)
class PlatformTurboConfig:
    checker: Any


_PLATFORM_CONFIG: dict[str, PlatformTurboConfig] = {
    "discord": PlatformTurboConfig(checker=DiscordChecker()),
    "instagram": PlatformTurboConfig(checker=InstagramChecker()),
    "roblox": PlatformTurboConfig(checker=RobloxChecker()),
    "minecraft": PlatformTurboConfig(checker=MinecraftChecker()),
    "tiktok": PlatformTurboConfig(checker=TikTokChecker()),
    "guns": PlatformTurboConfig(checker=GunsChecker()),
}


def is_turbo_platform(platform: str) -> bool:
    return platform in TURBO_PLATFORMS


def get_checker(platform: str) -> Any | None:
    cfg = _PLATFORM_CONFIG.get(platform)
    return cfg.checker if cfg else None


def get_workers(platform: str, discord_default: int = 3) -> int:
    """Legacy helper — runtime caps are applied after proxy budgets are known."""
    del platform
    return max(WORKERS_PER_PROXY, int(discord_default or WORKERS_PER_PROXY))


def workers_for_proxy_count(proxy_count: int, platform: str | None = None) -> int:
    n = max(1, int(proxy_count or 1))
    total = WORKERS_PER_PROXY * n
    if (platform or "").lower() == "discord":
        return min(total, DISCORD_MAX_WORKERS)
    return total
