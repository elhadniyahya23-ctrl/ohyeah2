from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

DEFAULT_LIMIT = {"interval_sec": 0.18, "max_concurrent": 12}

# Per-proxy-line limits — each proxy IP gets its own token bucket.
PLATFORM_LIMITS: dict[str, dict[str, float | int]] = {
    "discord": {
        "interval_sec": 0.28,
        "min_interval_sec": 0.15,
        "max_interval_sec": 1.0,
        "max_concurrent": 6,
        "workers_per_proxy": 6,
    },
    "roblox": {"interval_sec": 0.12, "max_concurrent": 20},
    "minecraft": {"interval_sec": 0.15, "max_concurrent": 16},
    "github": {"interval_sec": 0.12, "max_concurrent": 20},
    "reddit": {"interval_sec": 0.18, "max_concurrent": 12},
    "steam": {"interval_sec": 0.18, "max_concurrent": 12},
    "telegram": {"interval_sec": 0.22, "max_concurrent": 12},
    "instagram": {"interval_sec": 0.45, "max_concurrent": 8},
    "tiktok": {"interval_sec": 0.4, "max_concurrent": 8},
    "twitter": {"interval_sec": 0.28, "max_concurrent": 10},
    "snapchat": {"interval_sec": 0.28, "max_concurrent": 10},
    "youtube": {"interval_sec": 0.22, "max_concurrent": 12},
    "epic": {"interval_sec": 0.4, "max_concurrent": 8},
    "ubisoft": {"interval_sec": 0.5, "max_concurrent": 6},
    "guns": {"interval_sec": 0.2, "max_concurrent": 12},
    "whatsapp": {"interval_sec": 0.25, "max_concurrent": 10},
}


def get_platform_limits(platform: str) -> dict[str, float | int]:
    return PLATFORM_LIMITS.get(platform, DEFAULT_LIMIT)


def concurrency_for_platform(platform: str, ceiling: int) -> int:
    platform_max = int(get_platform_limits(platform)["max_concurrent"])
    return max(1, min(ceiling, platform_max))


def interval_for_platform(platform: str) -> float:
    return float(get_platform_limits(platform)["interval_sec"])


def min_interval_for_platform(platform: str) -> float:
    limits = get_platform_limits(platform)
    return float(limits.get("min_interval_sec", limits["interval_sec"]))


def max_interval_for_platform(platform: str) -> float:
    limits = get_platform_limits(platform)
    base = float(limits["interval_sec"])
    return float(limits.get("max_interval_sec", base * 3.0))


def rate_for_platform(platform: str) -> float:
    return 1.0 / interval_for_platform(platform)


def burst_for_platform(platform: str) -> int:
    return int(get_platform_limits(platform)["max_concurrent"])


def workers_per_proxy_for_platform(platform: str, ceiling: int) -> int:
    limits = get_platform_limits(platform)
    per_proxy = int(limits.get("workers_per_proxy", limits["max_concurrent"]))
    return max(1, min(ceiling, per_proxy))


def worker_count_for_platform(platform: str, num_proxies: int, max_workers: int, ceiling: int) -> int:
    per_proxy = workers_per_proxy_for_platform(platform, ceiling)
    return max(1, min(max_workers, per_proxy * max(1, num_proxies)))


@dataclass
class _LinePace:
    """Adaptive token bucket per proxy — speeds up on success, backs off on 429."""

    lock: asyncio.Lock
    rate_per_sec: float
    burst_capacity: int
    min_interval_sec: float | None = None
    max_interval_sec: float | None = None
    hard_pause_max_sec: float = 4.0
    recovery_interval_sec: float = 0.0
    long_pause_min_sec: float = 6.0
    long_pause_max_sec: float = 12.0
    long_retry_threshold_sec: float = 30.0
    tokens: float = 0.0
    last_refill: float = 0.0
    cooldown_until: float = 0.0
    _interval_sec: float = 0.0
    _success_streak: int = 0
    _hot_score: int = 0

    def __post_init__(self) -> None:
        self.tokens = 0.0
        self.last_refill = time.monotonic()
        base_interval = 1.0 / max(self.rate_per_sec, 0.05)
        self._interval_sec = base_interval
        if self.min_interval_sec is None:
            self.min_interval_sec = base_interval * 0.88
        if self.max_interval_sec is None:
            self.max_interval_sec = base_interval * 3.5

    @property
    def effective_rate_per_sec(self) -> float:
        return 1.0 / max(self._interval_sec, 0.05)

    @property
    def in_recovery(self) -> bool:
        return self._hot_score >= 4

    def on_success(self) -> None:
        self._success_streak += 1
        if self._success_streak >= 2:
            self._success_streak = 0
            self._interval_sec = max(
                self.min_interval_sec,
                self._interval_sec * 0.94,
            )

    def apply_rate_limit(self, retry_after: float | None) -> None:
        self._success_streak = 0
        if retry_after is not None and retry_after > 0:
            pause = retry_after if retry_after <= 4.0 else min(retry_after, self.hard_pause_max_sec)
            self._interval_sec = min(
                self.max_interval_sec,
                max(self._interval_sec * 1.15, self._interval_sec + 0.25),
            )
        else:
            pause = min(self.max_interval_sec, self._interval_sec * 1.5)
            self._interval_sec = min(self.max_interval_sec, self._interval_sec * 1.25)
        self.pause_for(pause)

    def schedule_wait(self, *, success: bool, raw_retry: float | None) -> float:
        """Seconds to wait before the next HTTP request on this proxy line."""
        if success:
            if self._hot_score > 0:
                self._hot_score = max(0, self._hot_score - 1)
                self.on_success()
                if self.recovery_interval_sec > 0:
                    return self.recovery_interval_sec
                return 0.0
            self._hot_score = 0
            self.on_success()
            return 0.0

        if self.recovery_interval_sec <= 0:
            if raw_retry is not None and raw_retry > 0:
                return min(raw_retry, self.hard_pause_max_sec)
            return self._interval_sec

        if raw_retry is not None and raw_retry > self.long_retry_threshold_sec:
            self._hot_score = min(10, self._hot_score + 2)
            return min(
                max(raw_retry * 0.08, self.long_pause_min_sec),
                self.long_pause_max_sec,
            )

        if raw_retry is not None and raw_retry > 0:
            self._hot_score = min(10, self._hot_score + 1)
            return min(raw_retry, self.hard_pause_max_sec)

        self._hot_score = min(10, self._hot_score + 1)
        return self._interval_sec

    async def acquire(self) -> None:
        while True:
            async with self.lock:
                now = time.monotonic()
                if now < self.cooldown_until:
                    wait = self.cooldown_until - now
                else:
                    rate = self.effective_rate_per_sec
                    elapsed = now - self.last_refill
                    self.tokens = min(
                        float(self.burst_capacity),
                        self.tokens + elapsed * rate,
                    )
                    self.last_refill = now
                    if self.tokens >= 1.0:
                        self.tokens -= 1.0
                        return
                    wait = (1.0 - self.tokens) / max(rate, 0.05)
            await asyncio.sleep(min(wait, 0.5))

    def pause_for(self, seconds: float) -> None:
        self.cooldown_until = max(self.cooldown_until, time.monotonic() + max(0.0, seconds))
        self.tokens = 0.0


class PlatformRateLimiter:
    """Global limiter kept for tests — production pacing is per proxy line."""

    def __init__(self) -> None:
        self._semaphores: dict[str, asyncio.Semaphore] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._last_request: dict[str, float] = {}

    def _limits(self, platform: str) -> dict[str, float | int]:
        return get_platform_limits(platform)

    def _ensure(self, platform: str) -> None:
        if platform in self._semaphores:
            return
        limits = self._limits(platform)
        self._semaphores[platform] = asyncio.Semaphore(int(limits["max_concurrent"]))
        self._locks[platform] = asyncio.Lock()

    async def acquire(self, platform: str) -> None:
        self._ensure(platform)
        await self._semaphores[platform].acquire()
        limits = self._limits(platform)
        interval = float(limits["interval_sec"])
        async with self._locks[platform]:
            now = time.monotonic()
            last = self._last_request.get(platform, 0.0)
            wait = interval - (now - last)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_request[platform] = time.monotonic()

    def release(self, platform: str) -> None:
        sem = self._semaphores.get(platform)
        if sem is not None:
            sem.release()


_limiter: PlatformRateLimiter | None = None


def get_rate_limiter() -> PlatformRateLimiter:
    global _limiter
    if _limiter is None:
        _limiter = PlatformRateLimiter()
    return _limiter
