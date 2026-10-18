import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from services.plans import user_has_active_plan
from services.sniper_cleanup import cleanup_live_snipers


class FakeRedis:
    def __init__(self, status: dict[str, dict]):
        self.status = {k: __import__("json").dumps(v) for k, v in status.items()}
        self.stopped: list[tuple[str, str]] = []

    async def scan(self, cursor=0, match=None, count=200):
        keys = [k for k in self.status if match is None or k.startswith(match.replace("*", ""))]
        # Simple match for sniper:status:*
        if match == "sniper:status:*":
            keys = [k for k in self.status if k.startswith("sniper:status:")]
        return 0, keys

    async def get(self, key):
        return self.status.get(key)


def test_expired_trial_has_no_active_plan():
    user = SimpleNamespace(
        username="hd4ngg",
        rank="Free Trial Expired",
        trial_used_seconds=300,
        plan_expires_at=None,
    )
    assert user_has_active_plan(user) is False


def test_cleanup_stops_orphans_and_expired(monkeypatch):
    redis = FakeRedis(
        {
            "sniper:status:orphantoken123:minecraft": {
                "state": "running",
                "checks_done": 50000,
            },
            "sniper:status:expiredtoken12:roblox": {
                "state": "running",
                "checks_done": 1000,
            },
            "sniper:status:goodtoken12345:roblox": {
                "state": "running",
                "checks_done": 100,
            },
            "sniper:status:idletoken12345:reddit": {
                "state": "idle",
            },
        }
    )

    expired = SimpleNamespace(
        id=1,
        username="hd4ngg",
        token="expiredtoken12",
        rank="Free Trial Expired",
        trial_used_seconds=300,
        plan_expires_at=None,
    )
    premium = SimpleNamespace(
        id=2,
        username="spoony",
        token="goodtoken12345",
        rank="Premium",
        trial_used_seconds=0,
        plan_expires_at=__import__("datetime").datetime(2099, 1, 1),
    )

    class FakeResult:
        def scalars(self):
            return SimpleNamespace(all=lambda: [expired, premium])

    db = AsyncMock()
    db.execute = AsyncMock(return_value=FakeResult())

    async def fake_stop(r, token, platform):
        redis.stopped.append((token, platform))
        return {"purged_queued": 0, "local_engine_stopped": False, "pool": "vps1"}

    monkeypatch.setattr(
        "services.sniper_cleanup.request_sniper_stop",
        fake_stop,
    )

    result = asyncio.run(cleanup_live_snipers(redis, db, mode="unauthorized"))
    assert result["stopped"] == 2
    stopped_pairs = set(redis.stopped)
    assert ("orphantoken123", "minecraft") in stopped_pairs
    assert ("expiredtoken12", "roblox") in stopped_pairs
    assert ("goodtoken12345", "roblox") not in stopped_pairs