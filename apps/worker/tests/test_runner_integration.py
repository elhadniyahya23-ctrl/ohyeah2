import asyncio
import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from worker.engine.runner import RunStats, SniperEngine
from worker.names_source import (
    FileNameStream,
    count_names_file,
    names_file_path,
    open_name_stream,
    resolve_names,
)
from worker.platforms.base import CheckOutcome, CheckResult


def test_count_names_file(tmp_path: Path):
    token = "user1"
    path = names_file_path(str(tmp_path), token)
    path.parent.mkdir(parents=True)
    path.write_text("a\n# skip\nb\n\nc\n", encoding="utf-8")
    assert count_names_file(str(tmp_path), token) == 3


@pytest.mark.asyncio
async def test_file_stream_skip(tmp_path: Path):
    token = "user1"
    path = names_file_path(str(tmp_path), token)
    path.parent.mkdir(parents=True)
    path.write_text("\n".join(f"n{i}" for i in range(100)), encoding="utf-8")

    stream = FileNameStream(path, skip=50)
    first = await stream.next_name()
    assert first == "n50"
    assert stream.position() == 51


def test_open_name_stream_from_file(tmp_path: Path):
    token = "tok"
    path = names_file_path(str(tmp_path), token)
    path.parent.mkdir(parents=True)
    path.write_text("one\ntwo\n", encoding="utf-8")
    stream, total = open_name_stream({"token": token, "offset": 1}, str(tmp_path))
    assert total == 2
    assert stream is not None


def test_resolve_names_prefers_file(tmp_path: Path):
    token = "user123"
    path = names_file_path(str(tmp_path), token)
    path.parent.mkdir(parents=True)
    path.write_text("alpha\nbeta\n", encoding="utf-8")
    job = {"token": token, "names": ["from-redis"]}
    assert resolve_names(job, str(tmp_path)) == ["alpha", "beta"]


def test_parse_retry_delay_caps_long_cooldowns():
    long_limit = CheckResult("n", CheckOutcome.RATE_LIMITED, "retry:1343")
    delay, raw = SniperEngine._parse_retry_delay(long_limit)
    assert raw == 1343.0
    assert delay <= 4.0

    short_limit = CheckResult("n", CheckOutcome.RATE_LIMITED, "retry:2.0")
    delay, raw = SniperEngine._parse_retry_delay(short_limit)
    assert raw == 2.0
    assert delay == 2.0


@pytest.mark.asyncio
async def test_runner_processes_all_names_with_many_proxies():
    redis_mock = AsyncMock()
    stop = asyncio.Event()
    pause = asyncio.Event()
    pause.set()
    engine = SniperEngine(redis_mock, stop_event=stop, pause_event=pause)

    class FakeChecker:
        platform = "discord"

        async def check(self, client, name: str) -> CheckResult:
            await asyncio.sleep(0)
            return CheckResult(name, CheckOutcome.TAKEN)

    from worker.engine import runner as runner_mod

    orig = runner_mod.get_checker
    runner_mod.get_checker = lambda _p: FakeChecker()

    proxies = [f"10.0.{i // 256}.{i % 256}:8080" for i in range(300)]
    job = {
        "platform": "discord",
        "names": [f"n{i}" for i in range(150)],
        "proxies": proxies,
    }

    await engine.run(job)
    runner_mod.get_checker = orig

    assert engine._stats.checks_done == 150


@pytest.mark.asyncio
async def test_runner_reads_names_from_shared_file():
    redis_mock = AsyncMock()
    stop = asyncio.Event()
    pause = asyncio.Event()
    pause.set()
    engine = SniperEngine(redis_mock, stop_event=stop, pause_event=pause)

    class FakeChecker:
        platform = "discord"

        async def check(self, client, name: str) -> CheckResult:
            return CheckResult(name, CheckOutcome.TAKEN)

    from worker.engine import runner as runner_mod

    orig = runner_mod.get_checker
    runner_mod.get_checker = lambda _p: FakeChecker()

    with tempfile.TemporaryDirectory() as tmp:
        token = "tok999"
        path = names_file_path(tmp, token)
        path.parent.mkdir(parents=True)
        path.write_text("\n".join(f"n{i}" for i in range(50)), encoding="utf-8")

        old_dir = runner_mod.settings.user_data_dir
        runner_mod.settings.user_data_dir = tmp
        try:
            job = {"platform": "discord", "token": token, "names": [], "proxies": []}
            await engine.run(job)
        finally:
            runner_mod.settings.user_data_dir = old_dir

    runner_mod.get_checker = orig
    assert engine._stats.checks_done == 50


@pytest.mark.asyncio
async def test_runner_resumes_from_offset():
    redis_mock = AsyncMock()
    stop = asyncio.Event()
    pause = asyncio.Event()
    pause.set()
    engine = SniperEngine(redis_mock, stop_event=stop, pause_event=pause)

    seen: list[str] = []

    class FakeChecker:
        platform = "discord"

        async def check(self, client, name: str) -> CheckResult:
            seen.append(name)
            return CheckResult(name, CheckOutcome.TAKEN)

    from worker.engine import runner as runner_mod

    orig = runner_mod.get_checker
    runner_mod.get_checker = lambda _p: FakeChecker()

    job = {
        "platform": "discord",
        "names": [f"n{i}" for i in range(10)],
        "proxies": [],
        "offset": 5,
        "resume_stats": {"checks_done": 5, "occupied": 5},
    }
    await engine.run(job)
    runner_mod.get_checker = orig

    assert set(seen) == {f"n{i}" for i in range(5, 10)}
    assert engine._stats.checks_done == 10


@pytest.mark.asyncio
async def test_runner_writes_stopped_status_on_manual_stop():
    redis_mock = AsyncMock()
    stop = asyncio.Event()
    pause = asyncio.Event()
    pause.set()
    engine = SniperEngine(redis_mock, stop_event=stop, pause_event=pause)

    class SlowChecker:
        platform = "discord"

        async def check(self, client, name: str) -> CheckResult:
            await asyncio.sleep(0.05)
            return CheckResult(name, CheckOutcome.TAKEN)

    from worker.engine import runner as runner_mod

    orig = runner_mod.get_checker
    runner_mod.get_checker = lambda _p: SlowChecker()

    stop.set()
    job = {
        "platform": "discord",
        "names": [f"n{i}" for i in range(20)],
        "proxies": [],
    }
    await engine.run(job)
    runner_mod.get_checker = orig

    final = json.loads(redis_mock.set.call_args_list[-1].args[1])
    assert final.get("state") == "stopped"
