"""
Reusable turbo sniper engine for usersniper.com backend.
HTTP via requests (sync) — concurrency via asyncio.to_thread.

Discord: suggestions-only on the hot path (attempt confirmations cause RL storms).
"""

from __future__ import annotations

import asyncio
import time
from collections import Counter, deque
from collections.abc import Awaitable, Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol, runtime_checkable

DEFAULT_WORKERS = 160
REQUEST_TIMEOUT = (2, 5)
# After this many PROXY_LATE on one name, keep retrying at the back of the queue
# but never starve fresh names (append, never appendleft).
_MAX_LATE_BEFORE_DEFER = 3
# After this many rate-limits on one name, skip it so the run cannot stall forever.
_MAX_RL_BEFORE_SKIP = 4


class Status(Enum):
    AVAILABLE = "available"
    TAKEN = "taken"
    RATE_LIMITED = "rate_limited"
    PROXY_LATE = "proxy_late"
    BLOCKED = "blocked"
    ERROR = "error"


# Only these advance the username cursor.
_PROGRESS_STATUSES = frozenset({Status.AVAILABLE, Status.TAKEN})


@dataclass(slots=True)
class CheckResult:
    target: str
    platform: str
    status: Status
    detail: str = ""


@dataclass(slots=True)
class RunStats:
    elapsed: float = 0.0
    checks: int = 0
    checks_per_sec: float = 0.0
    available: int = 0
    taken: int = 0
    rate_limited: int = 0
    rate_limit_pct: float = 0.0
    blocked: int = 0
    error: int = 0

    def to_dict(self) -> dict[str, float | int]:
        return {
            "elapsed": round(self.elapsed, 2),
            "checks": self.checks,
            "checks_per_sec": round(self.checks_per_sec, 2),
            "available": self.available,
            "taken": self.taken,
            "rate_limited": self.rate_limited,
            "rate_limit_pct": round(self.rate_limit_pct, 2),
            "blocked": self.blocked,
            "error": self.error,
        }


OnAvailableCallback = Callable[[CheckResult], Awaitable[None] | None]
OnResultCallback = Callable[[CheckResult], Awaitable[None] | None]


@runtime_checkable
class PlatformChecker(Protocol):
    platform: str

    def check(self, target: str, proxy_url: str) -> CheckResult: ...


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
    should_stop: Callable[[], bool | Awaitable[bool]] | None = None
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
        try:
            out = self.should_stop()
            if asyncio.iscoroutine(out):
                out = await out
            if out:
                self._stop.set()
                return True
        except Exception:
            pass
        return False

    async def run(
        self,
        targets: list[str],
        *,
        duration: float | None = None,
        max_checks: int | None = None,
    ) -> RunStats:
        if not targets:
            return RunStats()

        stats_counter: Counter[str] = Counter()
        next_idx = 0
        retry_q: deque[int] = deque()
        late_q: deque[int] = deque()
        late_counts: dict[int, int] = {}
        rl_counts: dict[int, int] = {}
        start = time.monotonic()
        end = (start + duration) if duration else None
        loop = asyncio.get_running_loop()
        recent: deque[str] = deque(maxlen=80)
        claim_lock = asyncio.Lock()

        with ThreadPoolExecutor(max_workers=max(self.workers, 1)) as pool:
            sem = asyncio.Semaphore(self.workers)
            pending: set[asyncio.Task[tuple[int, CheckResult, int]]] = set()
            slot_cycle = 0

            def _proxy_for(slot: int) -> tuple[str, int]:
                if self.lease_proxy is not None:
                    return self.lease_proxy()
                if self.proxy_for_slot is not None:
                    return self.proxy_for_slot(slot), -1
                return self.rotate_proxy(), -1

            def _adaptive_cap() -> int:
                """Back off under RL; circuit-break to 1 worker during storms."""
                if len(recent) < 10:
                    return self.workers
                rl = sum(1 for s in recent if s == "rate_limited")
                late = sum(1 for s in recent if s == "proxy_late")
                n = len(recent)
                rl_ratio = rl / n
                late_ratio = late / n
                if rl_ratio >= 0.6:
                    return 1
                if rl_ratio >= 0.45 or late_ratio >= 0.5:
                    return max(1, min(2, self.workers))
                if rl_ratio >= 0.3 or late_ratio >= 0.35:
                    return max(2, int(self.workers * 0.5))
                if rl_ratio >= 0.18 or late_ratio >= 0.22:
                    return max(2, int(self.workers * 0.75))
                return self.workers

            def _rl_storm_pause() -> float:
                """One cool-down when Discord is mostly 429 — then resume clean."""
                if len(recent) < 24:
                    return 0.0
                rl = sum(1 for s in recent if s == "rate_limited")
                ratio = rl / len(recent)
                if ratio >= 0.65:
                    return 2.5
                if ratio >= 0.5:
                    return 1.0
                return 0.0

            async def claim_index() -> int | None:
                nonlocal next_idx
                async with claim_lock:
                    # Always prefer fresh names — never let RL retries starve the run.
                    if next_idx < len(targets):
                        i = next_idx
                        next_idx += 1
                        return i
                    if retry_q:
                        return retry_q.popleft()
                    if late_q:
                        return late_q.popleft()
                    return None

            async def requeue(index: int, *, late: bool) -> None:
                async with claim_lock:
                    if late:
                        late_counts[index] = late_counts.get(index, 0) + 1
                        if late_counts[index] >= _MAX_LATE_BEFORE_DEFER:
                            late_q.append(index)
                        else:
                            retry_q.append(index)
                    else:
                        # Rate-limits: at most one retry, then skip (keeps CPS moving).
                        rl_counts[index] = rl_counts.get(index, 0) + 1
                        if rl_counts[index] < 2:
                            retry_q.append(index)

            async def worker(slot: int, index: int) -> tuple[int, CheckResult, int]:
                # Hold the semaphore only for the HTTP check — never while sleeping
                # on 429, or every worker stalls and CPS collapses.
                async with sem:
                    proxy, proxy_idx = _proxy_for(slot)
                    result = await loop.run_in_executor(
                        pool, self.checker.check, targets[index], proxy
                    )
                    if self.report_proxy is not None and proxy_idx >= 0:
                        try:
                            self.report_proxy(proxy_idx, result.status.value)
                        except Exception:
                            pass
                if result.status == Status.RATE_LIMITED:
                    pause = 0.35
                    detail = (result.detail or "").strip()
                    if detail.startswith("retry_after="):
                        try:
                            pause = max(0.2, min(float(detail.split("=", 1)[1]), 12.0))
                        except ValueError:
                            pass
                    await asyncio.sleep(pause)
                return index, result, proxy_idx

            storm_until = 0.0

            while not self._stop.is_set():
                if await self._stop_requested():
                    break
                if end and time.monotonic() >= end:
                    break
                productive = (
                    stats_counter[Status.AVAILABLE.value]
                    + stats_counter[Status.TAKEN.value]
                )
                if max_checks and productive >= max_checks:
                    break

                now = time.monotonic()
                if now < storm_until:
                    # Still drain in-flight work while cooling — never ignore pending.
                    if pending:
                        done, pending = await asyncio.wait(
                            pending, return_when=asyncio.FIRST_COMPLETED
                        )
                        for task in done:
                            try:
                                index, result, _proxy_idx = task.result()
                            except Exception:
                                continue
                            stats_counter["checks"] += 1
                            stats_counter[result.status.value] += 1
                            if result.status in _PROGRESS_STATUSES:
                                late_counts.pop(index, None)
                                rl_counts.pop(index, None)
                                if result.status == Status.AVAILABLE:
                                    await self._emit(self.on_available, result)
                            try:
                                await self._emit(self.on_result, result)
                            except Exception:
                                continue
                    else:
                        await asyncio.sleep(min(0.2, storm_until - now))
                    continue

                storm_pause = _rl_storm_pause()
                if storm_pause > 0:
                    # Cool once, drop RL retry junk, resume on fresh names.
                    storm_until = time.monotonic() + storm_pause
                    async with claim_lock:
                        retry_q.clear()
                    recent.clear()
                    continue

                active_workers = _adaptive_cap()
                while (
                    len(pending) < active_workers
                    and not self._stop.is_set()
                    and (end is None or time.monotonic() < end)
                    and time.monotonic() >= storm_until
                ):
                    index = await claim_index()
                    if index is None:
                        break
                    slot = slot_cycle % max(self.workers, 1)
                    slot_cycle += 1
                    pending.add(asyncio.create_task(worker(slot, index)))

                if not pending:
                    break

                done, pending = await asyncio.wait(
                    pending, return_when=asyncio.FIRST_COMPLETED
                )

                for task in done:
                    try:
                        index, result, _proxy_idx = task.result()
                    except Exception:
                        # One bad worker must not kill the whole Discord run.
                        continue
                    stats_counter["checks"] += 1
                    stats_counter[result.status.value] += 1
                    recent.append(result.status.value)
                    if result.status in _PROGRESS_STATUSES:
                        late_counts.pop(index, None)
                        rl_counts.pop(index, None)
                        if result.status == Status.AVAILABLE:
                            await self._emit(self.on_available, result)
                    else:
                        await requeue(
                            index,
                            late=result.status == Status.PROXY_LATE,
                        )
                    try:
                        await self._emit(self.on_result, result)
                    except Exception:
                        continue

            if pending:
                for task in pending:
                    task.cancel()
                await asyncio.gather(*pending, return_exceptions=True)

        elapsed = time.monotonic() - start
        checks = stats_counter["checks"]
        return RunStats(
            elapsed=elapsed,
            checks=checks,
            checks_per_sec=checks / elapsed if elapsed else 0.0,
            available=stats_counter[Status.AVAILABLE.value],
            taken=stats_counter[Status.TAKEN.value],
            rate_limited=stats_counter[Status.RATE_LIMITED.value],
            rate_limit_pct=(100 * stats_counter[Status.RATE_LIMITED.value] / checks)
            if checks
            else 0.0,
            blocked=stats_counter[Status.BLOCKED.value],
            error=stats_counter[Status.ERROR.value],
        )
