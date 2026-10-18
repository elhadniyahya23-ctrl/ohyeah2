from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

import httpx

from worker.config import settings
from worker.engine.proxy import build_proxy_urls
from worker.engine.ratelimit import (
    _LinePace,
    burst_for_platform,
    max_interval_for_platform,
    min_interval_for_platform,
    rate_for_platform,
    worker_count_for_platform,
)
from worker.names_source import NameStream, open_name_stream
from worker.platforms.base import CheckOutcome, CheckResult
from worker.platforms.registry import get_checker


@dataclass
class RunStats:
    checks_done: int = 0
    available: int = 0
    occupied: int = 0
    errors: int = 0
    rate_limits: int = 0
    proxy_misses: int = 0
    captures: list[dict] = field(default_factory=list)
    current_target: str | None = None
    start_time: float = field(default_factory=time.monotonic)

    @property
    def elapsed_seconds(self) -> int:
        return int(time.monotonic() - self.start_time)

    @property
    def checks_per_sec(self) -> float:
        elapsed = max(time.monotonic() - self.start_time, 0.001)
        return round(self.checks_done / elapsed, 2)

    @property
    def valid_checks(self) -> int:
        return self.available + self.occupied

    @property
    def valid_checks_per_sec(self) -> float:
        elapsed = max(time.monotonic() - self.start_time, 0.001)
        return round(self.valid_checks / elapsed, 2)

    @classmethod
    def from_resume(cls, data: dict | None) -> RunStats:
        if not data:
            return cls()
        return cls(
            checks_done=int(data.get("checks_done") or 0),
            available=int(data.get("available") or 0),
            occupied=int(data.get("occupied") or 0),
            errors=int(data.get("errors") or 0),
            rate_limits=int(data.get("rate_limits") or 0),
            proxy_misses=int(data.get("proxy_misses") or 0),
            captures=list(data.get("captures") or []),
        )


class SniperEngine:
    """Fixed worker pool + streamed names — reliable for multi-million lists."""

    @staticmethod
    def _parse_retry_delay(result: CheckResult) -> tuple[float, float | None]:
        """Return (effective_delay_sec, raw_delay_sec). Raw is set for retry:N details."""
        raw: float | None = None
        if result.detail.startswith("retry:"):
            try:
                raw = float(result.detail.split(":", 1)[1])
            except ValueError:
                pass
        if raw is not None:
            return min(raw, settings.rate_limit_backoff_max_sec), raw
        if result.outcome == CheckOutcome.RATE_LIMITED:
            return settings.rate_limit_backoff_sec, None
        return 0.75, None

    def __init__(self, redis, *, stop_event, pause_event):
        self.redis = redis
        self._stop = stop_event
        self._pause = pause_event
        self._thread_stop = asyncio.Event()
        self._pause_cleared = asyncio.Event()
        self._pause_cleared.set()
        self._stats = RunStats()
        self._stats_lock = asyncio.Lock()
        self._paces: list[_LinePace] = []

    async def update_status(self, platform: str, stats: RunStats, total_names: int, state: str):
        progress = 0.0
        if total_names > 0:
            progress = min(100.0, round(stats.checks_done / total_names * 100, 2))

        started_at = time.time()
        try:
            existing_raw = await self.redis.get(f"sniper:status:{platform}")
            if existing_raw:
                existing = json.loads(existing_raw)
                started_at = float(existing.get("started_at") or started_at)
        except Exception:
            pass

        payload = {
            "platform": platform,
            "state": state,
            "progress_pct": progress,
            "checks_done": stats.checks_done,
            "total_names": total_names,
            "checks_per_sec": stats.checks_per_sec,
            "valid_checks_per_sec": stats.valid_checks_per_sec,
            "recovery_mode": any(p.in_recovery for p in self._paces),
            "available": stats.available,
            "occupied": stats.occupied,
            "errors": stats.errors,
            "rate_limits": stats.rate_limits,
            "proxy_misses": stats.proxy_misses,
            "elapsed_seconds": stats.elapsed_seconds,
            "current_target": stats.current_target,
            "captures": stats.captures[-50:],
            "started_at": started_at,
        }
        await self.redis.set(f"sniper:status:{platform}", json.dumps(payload))

    async def _record_result(self, result: CheckResult) -> None:
        async with self._stats_lock:
            if result.outcome == CheckOutcome.AVAILABLE:
                self._stats.available += 1
                self._stats.captures.append(
                    {"name": result.name, "at": datetime.now(timezone.utc).isoformat()}
                )
            elif result.outcome == CheckOutcome.TAKEN:
                self._stats.occupied += 1
            elif result.outcome == CheckOutcome.RATE_LIMITED:
                self._stats.rate_limits += 1
            else:
                self._stats.errors += 1
            self._stats.checks_done += 1

    async def _check_name(
        self,
        checker,
        client: httpx.AsyncClient,
        name: str,
    ) -> CheckResult:
        try:
            return await checker.check(client, name)
        except httpx.ProxyError:
            async with self._stats_lock:
                self._stats.proxy_misses += 1
            return CheckResult(name, CheckOutcome.RATE_LIMITED, "proxy_error")
        except httpx.TimeoutException:
            async with self._stats_lock:
                self._stats.proxy_misses += 1
            return CheckResult(name, CheckOutcome.RATE_LIMITED, "proxy_error")
        except httpx.NetworkError:
            async with self._stats_lock:
                self._stats.proxy_misses += 1
            return CheckResult(name, CheckOutcome.RATE_LIMITED, "proxy_error")
        except Exception:
            return CheckResult(name, CheckOutcome.ERROR, "unexpected")

    async def _process_name(
        self,
        checker,
        client: httpx.AsyncClient,
        pace: _LinePace,
        name: str,
        *,
        can_switch_proxy: bool,
    ) -> bool:
        """Returns True if proxy should be switched (name will be retried)."""
        async with self._stats_lock:
            self._stats.current_target = name
        retries = 0
        last_outcome = CheckOutcome.ERROR

        while retries <= settings.max_retries_per_name and not self._thread_stop.is_set():
            await self._pause_cleared.wait()
            await pace.acquire()
            result = await self._check_name(checker, client, name)
            last_outcome = result.outcome

            if result.outcome in (CheckOutcome.RATE_LIMITED, CheckOutcome.ERROR):
                retries += 1
                if result.detail == "proxy_error":
                    if can_switch_proxy:
                        return True
                    if retries >= settings.max_retries_per_name:
                        await self._record_result(
                            CheckResult(name, CheckOutcome.ERROR, "proxy_error")
                        )
                        return False
                    await asyncio.sleep(1.0)
                    continue
                if result.outcome == CheckOutcome.RATE_LIMITED:
                    _, raw_delay = self._parse_retry_delay(result)
                    wait = pace.schedule_wait(success=False, raw_retry=raw_delay)
                    pace.pause_for(wait)
                    long_limit = (
                        raw_delay is not None
                        and raw_delay > settings.long_rate_limit_retry_after_sec
                    )
                    if long_limit:
                        await self._record_result(result)
                        return False
                    retry_cap = settings.max_retries_per_name
                    if retries >= retry_cap:
                        await self._record_result(result)
                        return False
                elif retries <= settings.max_retries_per_name:
                    await asyncio.sleep(0.75)
                if retries <= settings.max_retries_per_name:
                    continue

            wait = pace.schedule_wait(
                success=result.outcome in (CheckOutcome.TAKEN, CheckOutcome.AVAILABLE),
                raw_retry=None,
            )
            if wait > 0:
                pace.pause_for(wait)
            await self._record_result(result)
            return False

        async with self._stats_lock:
            if last_outcome == CheckOutcome.RATE_LIMITED:
                self._stats.rate_limits += 1
            else:
                self._stats.errors += 1
            self._stats.checks_done += 1
        return False

    async def _worker_loop(
        self,
        checker,
        proxy_urls: list[str | None],
        proxy_idx: int,
        pace: _LinePace,
        stream: NameStream,
    ) -> None:
        proxy_url = proxy_urls[proxy_idx]
        proxy_failures = 0

        limits = httpx.Limits(max_connections=4, max_keepalive_connections=2)
        connect_sec = 2.0 if proxy_url else min(3.0, settings.request_timeout_sec)
        timeout = httpx.Timeout(
            connect=connect_sec,
            read=settings.request_timeout_sec,
            write=settings.request_timeout_sec,
            pool=min(3.0, settings.request_timeout_sec),
        )

        while not self._thread_stop.is_set():
            try:
                client_ctx = httpx.AsyncClient(
                    proxy=proxy_url,
                    timeout=timeout,
                    limits=limits,
                    follow_redirects=True,
                )
            except httpx.InvalidURL:
                proxy_idx = (proxy_idx + 1) % len(proxy_urls)
                proxy_url = proxy_urls[proxy_idx]
                continue

            async with client_ctx as client:
                pending_name: str | None = None
                while not self._thread_stop.is_set():
                    await self._pause_cleared.wait()
                    if pending_name is not None:
                        name = pending_name
                        pending_name = None
                    else:
                        name = await stream.next_name()
                        if name is None:
                            return

                    should_switch = await self._process_name(
                        checker,
                        client,
                        pace,
                        name,
                        can_switch_proxy=len(proxy_urls) > 1,
                    )
                    if should_switch:
                        proxy_failures += 1
                        if len(proxy_urls) > 1:
                            pending_name = name
                            proxy_idx = (proxy_idx + 1) % len(proxy_urls)
                            proxy_url = proxy_urls[proxy_idx]
                            proxy_failures = 0
                            break

    async def _run_async(self, job: dict, stream: NameStream) -> None:
        platform = job["platform"]
        checker = get_checker(platform)
        if checker is None:
            return

        user_proxies = job.get("proxies") or []
        include_direct = platform != "discord" or not user_proxies
        proxy_urls = build_proxy_urls(
            user_proxies,
            settings.max_proxy_lines,
            include_direct_fallback=include_direct,
        )
        num_proxies = len(proxy_urls)
        worker_count = worker_count_for_platform(
            platform,
            num_proxies,
            settings.max_workers,
            settings.workers_per_proxy_line,
        )

        rate = rate_for_platform(platform)
        burst = burst_for_platform(platform)
        min_iv = min_interval_for_platform(platform)
        max_iv = max_interval_for_platform(platform)
        recovery_iv = settings.discord_recovery_interval_sec if platform == "discord" else 0.0
        paces = [
            _LinePace(
                lock=asyncio.Lock(),
                rate_per_sec=rate,
                burst_capacity=burst,
                min_interval_sec=min_iv,
                max_interval_sec=max_iv,
                hard_pause_max_sec=settings.rate_limit_hard_pause_max_sec,
                recovery_interval_sec=recovery_iv,
                long_pause_min_sec=settings.long_rate_limit_pause_min_sec,
                long_pause_max_sec=settings.long_rate_limit_pause_max_sec,
                long_retry_threshold_sec=settings.long_rate_limit_retry_after_sec,
            )
            for _ in range(num_proxies)
        ]
        self._paces = paces

        await asyncio.gather(
            *(
                self._worker_loop(
                    checker,
                    proxy_urls,
                    slot % num_proxies,
                    paces[slot % num_proxies],
                    stream,
                )
                for slot in range(worker_count)
            ),
            return_exceptions=True,
        )

    async def _status_flush_loop(self, platform: str, total: int) -> None:
        try:
            while not self._stop.is_set():
                await self.update_status(platform, self._stats, total, "running")
                await asyncio.sleep(settings.status_flush_interval_sec)
        except asyncio.CancelledError:
            pass

    async def _bridge_control_events(self) -> None:
        try:
            while True:
                if self._stop.is_set():
                    self._thread_stop.set()
                    break
                if self._pause.is_set():
                    self._pause_cleared.set()
                else:
                    self._pause_cleared.clear()
                await asyncio.sleep(0.05)
        except asyncio.CancelledError:
            self._thread_stop.set()

    def _final_state(self, total: int) -> str:
        if self._stop.is_set():
            return "stopped"
        if self._stats.checks_done >= total:
            return "completed"
        return "interrupted"

    async def run(self, job: dict):
        platform = job["platform"]
        stream, total = open_name_stream(job, settings.user_data_dir)
        job_total = int(job.get("total_names") or 0)

        if stream is None or total == 0:
            if job_total > 0:
                await self.update_status(platform, RunStats(errors=1), job_total, "interrupted")
            else:
                await self.update_status(platform, RunStats(), 0, "idle")
            return

        checker = get_checker(platform)
        if checker is None:
            await self.update_status(platform, RunStats(errors=1), total, "idle")
            return

        self._thread_stop.clear()
        self._pause_cleared.set()
        self._stats = RunStats.from_resume(job.get("resume_stats"))
        if self._stats.checks_done == 0:
            self._stats.start_time = time.monotonic()

        await self.update_status(platform, self._stats, total, "running")

        bridge_task = asyncio.create_task(self._bridge_control_events())
        flush_task = asyncio.create_task(self._status_flush_loop(platform, total))

        try:
            await self._run_async(job, stream)
        finally:
            self._thread_stop.set()
            bridge_task.cancel()
            flush_task.cancel()
            await asyncio.gather(bridge_task, flush_task, return_exceptions=True)

        async with self._stats_lock:
            self._stats.current_target = None
        final_state = "stopped" if self._stop.is_set() else self._final_state(total)
        await self.update_status(platform, self._stats, total, final_state)
