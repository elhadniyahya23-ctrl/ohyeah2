from sniper.registry import COMING_SOON_PLATFORMS, TURBO_PLATFORMS, get_checker, get_workers


def test_turbo_platforms():
    assert TURBO_PLATFORMS == frozenset(
        {
            "discord",
            "roblox",
            "minecraft",
            "instagram",
            "tiktok",
            "github",
            "reddit",
            "guns",
        }
    )


def test_coming_soon_excludes_turbo():
    assert TURBO_PLATFORMS.isdisjoint(COMING_SOON_PLATFORMS)
    assert "tiktok" not in COMING_SOON_PLATFORMS
    assert "ubisoft" in COMING_SOON_PLATFORMS


def test_discord_workers_respect_settings_default():
    assert get_workers("discord", 160) == 160
    assert get_workers("discord", 82) == 82


def test_other_platforms_have_lower_worker_counts():
    assert get_workers("roblox", 160) == 48
    assert get_workers("instagram", 160) == 16
    assert get_workers("tiktok", 160) == 16
    assert get_workers("minecraft", 160) == 48


def test_every_turbo_platform_has_checker():
    for platform in TURBO_PLATFORMS:
        checker = get_checker(platform)
        assert checker is not None
        assert checker.platform == platform
