import asyncio
import time

import pytest

from worker.engine.ratelimit import PlatformRateLimiter, _LinePace, rate_for_platform


@pytest.mark.asyncio
async def test_rate_limiter_respects_concurrency():
    limiter = PlatformRateLimiter()
    active = 0
    max_active = 0
    lock = asyncio.Lock()

    async def worker() -> None:
        nonlocal active, max_active
        await limiter.acquire("instagram")
        async with lock:
            active += 1
            max_active = max(max_active, active)
        await asyncio.sleep(0.05)
        async with lock:
            active -= 1
        limiter.release("instagram")

    await asyncio.gather(*[worker() for _ in range(10)])
    assert max_active <= 8


@pytest.mark.asyncio
async def test_line_pace_strict_interval():
    pace = _LinePace(
        lock=asyncio.Lock(),
        rate_per_sec=2.0,
        burst_capacity=1,
    )
    start = asyncio.get_event_loop().time()
    await pace.acquire()
    await pace.acquire()
    elapsed = asyncio.get_event_loop().time() - start
    assert elapsed >= 0.4


@pytest.mark.asyncio
async def test_line_pace_honors_cooldown():
    pace = _LinePace(
        lock=asyncio.Lock(),
        rate_per_sec=10.0,
        burst_capacity=1,
    )
    pace.pause_for(0.2)
    start = asyncio.get_event_loop().time()
    await pace.acquire()
    elapsed = asyncio.get_event_loop().time() - start
    assert elapsed >= 0.15


@pytest.mark.asyncio
async def test_line_pace_speeds_up_after_success_streak():
    pace = _LinePace(
        lock=asyncio.Lock(),
        rate_per_sec=1.0 / 0.28,
        burst_capacity=1,
        min_interval_sec=0.15,
        max_interval_sec=1.0,
    )
    assert pace._interval_sec == pytest.approx(0.28, rel=0.01)
    pace.on_success()
    pace.on_success()
    assert pace._interval_sec == pytest.approx(0.28 * 0.94, rel=0.01)
    pace.on_success()
    pace.on_success()
    assert pace._interval_sec == pytest.approx(0.28 * 0.94 * 0.94, rel=0.01)


@pytest.mark.asyncio
async def test_line_pace_non_discord_skips_recovery_wait():
    pace = _LinePace(
        lock=asyncio.Lock(),
        rate_per_sec=2.0,
        burst_capacity=1,
        recovery_interval_sec=0.0,
    )
    pace._hot_score = 5
    assert pace.schedule_wait(success=True, raw_retry=None) == 0.0


@pytest.mark.asyncio
async def test_line_pace_recovery_wait_on_long_limit():
    pace = _LinePace(
        lock=asyncio.Lock(),
        rate_per_sec=1.0,
        burst_capacity=1,
        recovery_interval_sec=4.0,
        long_pause_min_sec=6.0,
        long_pause_max_sec=12.0,
        long_retry_threshold_sec=30.0,
    )
    wait = pace.schedule_wait(success=False, raw_retry=800.0)
    assert 6.0 <= wait <= 12.0
    pace.schedule_wait(success=False, raw_retry=800.0)
    assert pace.in_recovery


@pytest.mark.asyncio
async def test_line_pace_success_after_recovery_waits():
    pace = _LinePace(
        lock=asyncio.Lock(),
        rate_per_sec=1.0,
        burst_capacity=1,
        recovery_interval_sec=4.0,
    )
    pace._hot_score = 5
    wait = pace.schedule_wait(success=True, raw_retry=None)
    assert wait == 4.0
