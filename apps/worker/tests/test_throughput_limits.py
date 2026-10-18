from worker.engine.ratelimit import concurrency_for_platform, get_platform_limits, interval_for_platform


def test_concurrency_capped_by_platform():
    assert concurrency_for_platform("discord", 50) == 6
    assert concurrency_for_platform("instagram", 50) == 8
    assert concurrency_for_platform("roblox", 3) == 3


def test_interval_for_platform():
    assert interval_for_platform("discord") == 0.28
    assert interval_for_platform("unknown") == 0.18


def test_discord_adaptive_interval_bounds():
    from worker.engine.ratelimit import max_interval_for_platform, min_interval_for_platform

    assert min_interval_for_platform("discord") == 0.15
    assert max_interval_for_platform("discord") == 1.0


def test_worker_count_for_discord_one_per_proxy():
    from worker.engine.ratelimit import worker_count_for_platform

    assert worker_count_for_platform("discord", 1, 48, 8) == 6
    assert worker_count_for_platform("discord", 5, 48, 8) == 30
    assert worker_count_for_platform("roblox", 5, 48, 8) == 40


def test_all_registered_platforms_have_limits():
    from worker.platforms.registry import all_platforms

    for platform in all_platforms():
        limits = get_platform_limits(platform)
        assert limits["max_concurrent"] >= 1
        assert limits["interval_sec"] > 0
