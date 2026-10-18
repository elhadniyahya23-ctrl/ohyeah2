"""
SNIPER ENGINE — aiohttp workers with adaptive concurrency.

Soft failures (late / RL) retry without starving fresh names.
Workers scale down under late/RL storms and ramp back up.
"""

from __future__ import annotations

import asyncio
import time
from collections import Counter, deque
from collections.abc import Awaitable, Callable, Iterator
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

import aiohttp

from sniper.types import CheckResult, RunStats, Status

DEFAULT_WORKERS = 3
REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=4.0, connect=1.5)

_PROGRESS_STATUSES = frozenset({Status.AVAILABLE, Status.TAKEN})
_MAX_LATE_RETRIES = 2
_MAX_RL_RETRIES = 1
_MAX_ERROR_RETRIES = 8


@runtime_checkable
class PlatformChecker(Protocol):
    platform: str

    async def check(
        self,
        session: aiohttp.ClientSession,
        target: str,
        proxy_url: str,
    ) -> CheckResult: ...


OnAvailableCallback = Callable[[CheckResult], Awaitable[None] | None]
OnResultCallback = Callable[[CheckResult], Awaitable[None] | None]
ShouldStopCallback = Callable[[], Awaitable[bool] | bool]
OnSoftFailCallback = Callable[[str], None]


@dataclass
class TurboEngine:
    checker: PlatformChecker
    rotate_proxy: Callable[[], str]
    workers: int = DEFAULT_WORKERS
    proxy_for_slot: Callable[[int], str] | None = None
    # Optional scored proxy lease: returns (proxy_url, line_index).
    lease_proxy: Callable[[], tuple[str, int]] | None = None
    report_proxy: Callable[[int, str], None] | None = None
    on_available: OnAvailableCallback | None = None
    on_result: OnResultCallback | None = None
    should_stop: ShouldStopCallback | None = None
    on_soft_fail: OnSoftFailCallback | None = None
    _stop: asyncio.Event = field(default_factory=asyncio.Event, init=False)

    def stop(self) -> None:
        self._stop.set()

    async def _emit(self, cb: Callable | None, result: CheckResult) -> None:
        if cb is None:
            return
        out = cb(result)
        if asyncio.iscoroutine(out):
            await out

    async def _stop_requested(self) -> bool:
        if self._stop.is_set():
            return True
        if self.should_stop is None:
            return False
        out = self.should_stop()
        if asyncio.iscoroutine(out):
            return bool(await out)
        return bool(out)

    def _adaptive_cap(self, recent: deque[str], max_workers: int) -> int:
        """Lower concurrency when late/RL dominate — protects valid CPS."""
        if len(recent) < 8:
            return max_workers
        n = len(recent)
        late = sum(1 for s in recent if s == "proxy_late")
        rl = sum(1 for s in recent if s == "rate_limited")
        late_r = late / n
        rl_r = rl / n
        floor = 2 if max_workers >= 3 else 1
        # Discord 429 storms: shed load but keep enough workers for ≥2–3 CPS.
        if rl_r >= 0.5:
            return floor
        if rl_r >= 0.32 or late_r >= 0.55:
            return max(floor, max_workers // 2)
        if rl_r >= 0.2 or late_r >= 0.35:
            return max(floor, int(max_workers * 0.65))
        if rl_r >= 0.12 or late_r >= 0.22:
            return max(floor, int(max_workers * 0.8))
        return max_workers

    async def run(
        self,
        targets: list[str] | None = None,
        *,
        name_iter: Iterator[str] | None = None,
        total: int | None = None,
    ) -> RunStats:
        """Run until stop or every name has a definitive AVAILABLE/TAKEN result.

        Pass ``name_iter`` + ``total`` to stream from disk without loading the
        full list into memory (multi-million name lists).
        """
        streaming = name_iter is not None
        if streaming:
            total_names = int(total or 0)
            if total_names <= 0:
                return RunStats()
            feed: Iterator[str] | None = iter(name_iter)
            next_idx = 0
        else:
            targets = targets or []
            if not targets:
                return RunStats()
            total_names = len(targets)
            feed = None
            next_idx = 0

        max_workers = max(1, int(self.workers or DEFAULT_WORKERS))
        stats_counter: Counter[str] = Counter()
        retry_counts: dict[str, int] = {}
        retry_q: deque[str] = deque()
        recent: deque[str] = deque(maxlen=48)
        in_flight_targets: dict[asyncio.Task[CheckResult], str] = {}
        start = time.monotonic()
        connector = aiohttp.TCPConnector(
            limit=max_workers,
            limit_per_host=max_workers,
            ttl_dns_cache=300,
            # FlashProxy residential exits: fresh connection per check is more
            # reliable than keep-alive through rotating tunnels.
            force_close=True,
            enable_cleanup_closed=True,
        )
        async with aiohttp.ClientSession(
            connector=connector, timeout=REQUEST_TIMEOUT
        ) as session:
            sem = asyncio.Semaphore(max_workers)
            pending: set[asyncio.Task[CheckResult]] = set()
            rl_cool_until = 0.0

            async def check_one(target: str) -> CheckResult:
                async with sem:
                    proxy_idx = -1
                    if self.lease_proxy is not None:
                        proxy, proxy_idx = self.lease_proxy()
                    elif self.proxy_for_slot is not None:
                        # Slot sticky exits — use a rotating counter as slot id.
                        proxy = self.proxy_for_slot(stats_counter["attempts"])
                    else:
                        proxy = self.rotate_proxy()
                    result = await self.checker.check(session, target, proxy)
                    if self.report_proxy is not None and proxy_idx >= 0:
                        try:
                            self.report_proxy(proxy_idx, result.status.value)
                        except Exception:
                            pass
                    return result

            def spawn(target: str) -> None:
                task = asyncio.create_task(check_one(target))
                pending.add(task)
                in_flight_targets[task] = target

            def pull_next_target() -> str | None:
                nonlocal next_idx
                # Prefer fresh names so late retries cannot monopolize the fleet.
                if feed is not None:
                    try:
                        return next(feed)
                    except StopIteration:
                        pass
                elif next_idx < total_names:
                    target = targets[next_idx]  # type: ignore[index]
                    next_idx += 1
                    return target
                if retry_q:
                    return retry_q.popleft()
                return None

            def queue_soft_retry(target: str, status: str, detail: str = "") -> None:
                name = (target or "").strip()
                if not name:
                    return
                if self.on_soft_fail is not None:
                    try:
                        self.on_soft_fail(status)
                    except Exception:
                        pass
                retry_counts[name] = retry_counts.get(name, 0) + 1
                # Dead proxy auth / traffic exhausted: don't burn the fleet retrying.
                if "proxy_auth" in (detail or "") or "traffic_exhausted" in (
                    detail or ""
                ).lower():
                    limit = 1
                elif status == "rate_limited":
                    limit = _MAX_RL_RETRIES
                elif status == "proxy_late":
                    limit = _MAX_LATE_RETRIES
                else:
                    limit = _MAX_ERROR_RETRIES
                if retry_counts[name] <= limit:
                    retry_q.append(name)
                else:
                    stats_counter["progress"] += 1
                    stats_counter["error"] += 1

            while not self._stop.is_set() and stats_counter["progress"] < total_names:
                if await self._stop_requested():
                    break
                now = time.monotonic()
                if now < rl_cool_until:
                    # Cool the whole fleet after 429 — drain in-flight only.
                    if pending:
                        done, pending = await asyncio.wait(
                            pending, return_when=asyncio.FIRST_COMPLETED
                        )
                        for task in done:
                            target = in_flight_targets.pop(task, "?")
                            try:
                                result = task.result()
                            except Exception as exc:
                                detail = (str(exc).strip() or type(exc).__name__)[:120]
                                result = CheckResult(
                                    target,
                                    getattr(self.checker, "platform", "unknown"),
                                    Status.PROXY_LATE,
                                    detail,
                                )
                            stats_counter["attempts"] += 1
                            stats_counter[result.status.value] += 1
                            recent.append(result.status.value)
                            if result.status == Status.AVAILABLE:
                                await self._emit(self.on_available, result)
                            await self._emit(self.on_result, result)
                            if result.status in _PROGRESS_STATUSES:
                                retry_counts.pop(result.target or target, None)
                                stats_counter["progress"] += 1
                    else:
                        await asyncio.sleep(min(0.2, rl_cool_until - now))
                    continue

                active = self._adaptive_cap(recent, max_workers)
                while (
                    len(pending) < active
                    and not self._stop.is_set()
                    and stats_counter["progress"] + len(pending) < total_names
                ):
                    target = pull_next_target()
                    if target is None:
                        break
                    spawn(target)
                if not pending:
                    break
                done, pending = await asyncio.wait(
                    pending, return_when=asyncio.FIRST_COMPLETED
                )
                for task in done:
                    target = in_flight_targets.pop(task, "?")
                    try:
                        result = task.result()
                    except Exception as exc:
                        detail = (str(exc).strip() or type(exc).__name__)[:120]
                        result = CheckResult(
                            target,
                            getattr(self.checker, "platform", "unknown"),
                            Status.PROXY_LATE,
                            detail,
                        )
                    stats_counter["attempts"] += 1
                    stats_counter[result.status.value] += 1
                    recent.append(result.status.value)
                    if result.status == Status.AVAILABLE:
                        await self._emit(self.on_available, result)
                    await self._emit(self.on_result, result)

                    if result.status in _PROGRESS_STATUSES:
                        retry_counts.pop(result.target or target, None)
                        stats_counter["progress"] += 1
                    elif not self._stop.is_set() and not await self._stop_requested():
                        if result.status == Status.RATE_LIMITED:
                            pause = 0.35
                            detail = (result.detail or "").strip()
                            if detail.startswith("retry_after="):
                                try:
                                    pause = max(
                                        0.25, min(float(detail.split("=", 1)[1]), 1.4)
                                    )
                                except ValueError:
                                    pass
                            rl_cool_until = max(
                                rl_cool_until, time.monotonic() + pause
                            )
                        queue_soft_retry(
                            result.target or target,
                            result.status.value,
                            result.detail or "",
                        )

            if pending:
                for task in pending:
                    task.cancel()
                await asyncio.gather(*pending, return_exceptions=True)

        elapsed = time.monotonic() - start
        checks = stats_counter["progress"]
        attempts = stats_counter["attempts"]
        return RunStats(
            elapsed=elapsed,
            checks=checks,
            checks_per_sec=checks / elapsed if elapsed else 0.0,
            available=stats_counter["available"],
            taken=stats_counter["taken"],
            rate_limited=stats_counter["rate_limited"],
            rate_limit_pct=(100 * stats_counter["rate_limited"] / attempts)
            if attempts
            else 0.0,
            blocked=stats_counter["blocked"],
            error=stats_counter["error"],
            proxy_late=stats_counter["proxy_late"],
        )


__all__ = ["DEFAULT_WORKERS", "PlatformChecker", "TurboEngine"]
