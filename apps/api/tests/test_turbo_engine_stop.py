import asyncio
import time

from sniper.turbo_engine import CheckResult, Status, TurboEngine


class FakeChecker:
    platform = "test"

    def __init__(self) -> None:
        self.calls = 0

    def check(self, target: str, proxy_url: str) -> CheckResult:
        self.calls += 1
        time.sleep(0.01)
        return CheckResult(target, self.platform, Status.TAKEN)


def test_turbo_engine_should_stop_halts_run():
    stop_after = {"n": 0}

    async def should_stop() -> bool:
        return stop_after["n"] >= 3

    async def on_result(result):
        stop_after["n"] += 1

    async def run():
        engine = TurboEngine(
            checker=FakeChecker(),
            rotate_proxy=lambda: "http://127.0.0.1:8080",
            workers=4,
            on_result=on_result,
            should_stop=should_stop,
        )
        return await engine.run(["a", "b", "c"])

    stats = asyncio.run(run())
    assert stats.checks <= 6
    assert stop_after["n"] >= 3
