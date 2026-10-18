from sniper.vps_pools import (
    ALL_PLATFORMS,
    VPS1_PLATFORMS,
    VPS2_PLATFORMS,
    VPS3_PLATFORMS,
    get_vps_pool,
    is_remote_pool,
    pools_for_platform,
    queue_key_for_platform,
    queue_keys_for_platform,
)


def test_all_sixteen_platforms_assigned():
    assert len(ALL_PLATFORMS) == 16
    covered = VPS1_PLATFORMS | VPS2_PLATFORMS | VPS3_PLATFORMS
    assert covered == ALL_PLATFORMS


def test_discord_on_hostinger_and_vultr():
    assert pools_for_platform("discord") == ["vps1", "vps2"]
    assert get_vps_pool("discord") == "vps1"
    assert "discord" in VPS1_PLATFORMS
    assert "discord" in VPS2_PLATFORMS
    assert "discord" not in VPS3_PLATFORMS
    assert not is_remote_pool("vps1")
    assert is_remote_pool("vps2")


def test_gaming_platforms_on_hostinger_vps3():
    for platform in ("roblox", "minecraft", "github", "reddit", "steam", "epic", "ubisoft"):
        assert get_vps_pool(platform) == "vps3"
        assert platform in VPS3_PLATFORMS


def test_hostinger_social_platforms():
    for platform in (
        "telegram",
        "whatsapp",
        "instagram",
        "tiktok",
        "twitter",
        "snapchat",
        "youtube",
        "guns",
    ):
        assert get_vps_pool(platform) == "vps3"


def test_queue_keys():
    assert queue_key_for_platform("discord") == "sniper:queue:vps1"
    assert queue_keys_for_platform("discord") == [
        "sniper:queue:vps1",
        "sniper:queue:vps2",
    ]
    assert queue_key_for_platform("roblox") == "sniper:queue:vps3"
    assert queue_key_for_platform("instagram") == "sniper:queue:vps3"
