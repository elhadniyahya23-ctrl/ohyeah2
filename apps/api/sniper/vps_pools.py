from __future__ import annotations

"""Maps every platform to the Hostinger + Vultr sniper fleets (GCP dropped).

VPS1 Hostinger — Discord fleet (sniper-node), shared with control API.
VPS2 Vultr — Discord fleet (separate egress IP) — least-busy with VPS1.
VPS3 Hostinger — social + gaming fleet (sniper-social containers).
"""

from typing import Literal

VpsPool = Literal["vps1", "vps2", "vps3"]

ALL_PLATFORMS: frozenset[str] = frozenset(
    {
        "discord",
        "roblox",
        "minecraft",
        "telegram",
        "whatsapp",
        "instagram",
        "tiktok",
        "twitter",
        "github",
        "snapchat",
        "steam",
        "reddit",
        "youtube",
        "guns",
        "epic",
        "ubisoft",
    }
)

# Discord on both Hostinger and Vultr — pick least-busy at enqueue time.
VPS1_PLATFORMS: frozenset[str] = frozenset({"discord"})
VPS2_PLATFORMS: frozenset[str] = frozenset({"discord"})

# Hostinger social + gaming fleet (sniper-social containers, vps3 queue key).
VPS3_PLATFORMS: frozenset[str] = frozenset(
    {
        "telegram",
        "whatsapp",
        "instagram",
        "tiktok",
        "twitter",
        "snapchat",
        "youtube",
        "guns",
        "roblox",
        "minecraft",
        "github",
        "reddit",
        "steam",
        "epic",
        "ubisoft",
    }
)

# Pools that do not share Hostinger USER_DATA_DIR — job payload must carry names
# (or load them from Redis — see load_targets_from_redis).
REMOTE_POOLS: frozenset[VpsPool] = frozenset({"vps2"})

POOL_PLATFORMS: dict[VpsPool, frozenset[str]] = {
    "vps1": VPS1_PLATFORMS,
    "vps2": VPS2_PLATFORMS,
    "vps3": VPS3_PLATFORMS,
}

QUEUE_KEYS: dict[VpsPool, str] = {
    "vps1": "sniper:queue:vps1",
    "vps2": "sniper:queue:vps2",
    "vps3": "sniper:queue:vps3",
}

# Platforms that can run on more than one pool (least-busy routing).
MULTI_POOL_PLATFORMS: frozenset[str] = frozenset({"discord"})


def pools_for_platform(platform: str) -> list[VpsPool]:
    """All pools that accept this platform, in preference order."""
    pools: list[VpsPool] = []
    for pool, plats in POOL_PLATFORMS.items():
        if platform in plats:
            pools.append(pool)
    if not pools:
        raise ValueError(f"Unknown platform: {platform}")
    return pools


def get_vps_pool(platform: str) -> VpsPool:
    """Primary / default pool (first in preference order)."""
    return pools_for_platform(platform)[0]


def queue_key_for_platform(platform: str) -> str:
    return QUEUE_KEYS[get_vps_pool(platform)]


def queue_keys_for_platform(platform: str) -> list[str]:
    return [QUEUE_KEYS[p] for p in pools_for_platform(platform)]


def pool_supports_platform(pool: str, platform: str) -> bool:
    return platform in POOL_PLATFORMS.get(pool, frozenset())  # type: ignore[arg-type]


def is_remote_pool(pool: str) -> bool:
    return pool in REMOTE_POOLS
