import asyncio
import time

from sniper.turbo_engine import CheckResult, Status, TurboEngine


class FlakyThenOk:
    platform = "test"

    def __init__(self) -> None:
        self.calls = 0

    def check(self, target: str, proxy_url: str) -> CheckResult:
        self.calls += 1
        # First two attempts on "a" fail; then succeed.
        if target == "a" and self.calls <= 2:
            return CheckResult(target, self.platform, Status.RATE_LIMITED, "retry_after=0.01")
        time.sleep(0.005)
        return CheckResult(target, self.platform, Status.TAKEN)


def test_rate_limited_does_not_skip_name():
    checker = FlakyThenOk()

    async def run():
        engine = TurboEngine(
            checker=checker,
            rotate_proxy=lambda: "http://127.0.0.1:8080",
            workers=2,
        )
        return await engine.run(["a", "b"], max_checks=2)

    stats = asyncio.run(run())
    assert stats.taken == 2
    assert stats.rate_limited >= 1
    assert checker.calls >= 3


class AlwaysLateThenOk:
    """First name is always late; second name succeeds immediately."""

    platform = "test"

    def __init__(self) -> None:
        self.order: list[str] = []

    def check(self, target: str, proxy_url: str) -> CheckResult:
        self.order.append(target)
        if target == "stuck":
            return CheckResult(target, self.platform, Status.PROXY_LATE, "timeout")
        return CheckResult(target, self.platform, Status.TAKEN)


def test_proxy_late_does_not_starve_fresh_names():
    checker = AlwaysLateThenOk()

    async def run():
        engine = TurboEngine(
            checker=checker,
            rotate_proxy=lambda: "http://127.0.0.1:8080",
            workers=2,
        )
        # Stop once we have one productive check (the fresh name).
        return await engine.run(["stuck", "fresh"], max_checks=1)

    stats = asyncio.run(run())
    assert stats.taken == 1
    # Fresh name must be attempted even while "stuck" keeps timing out.
    assert "fresh" in checker.order
