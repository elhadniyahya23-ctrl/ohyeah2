import asyncio
import json

from services.turbo_sniper_service import _persist_status


class FakeRedis:
    def __init__(self, initial: dict | None = None) -> None:
        self.store: dict[str, str] = {}
        if initial is not None:
            self.store["sniper:status:tok:discord"] = json.dumps(initial)

    async def get(self, key: str):
        return self.store.get(key)

    async def set(self, key: str, value: str):
        self.store[key] = value


def test_persist_status_preserves_higher_trial_billed_seconds():
    redis = FakeRedis(
        {
            "session_id": "abc",
            "state": "running",
            "trial_billed_seconds": 40,
            "trial_billed": False,
            "checks_done": 10,
        }
    )

    async def run():
        await _persist_status(
            redis,
            "tok",
            "discord",
            {
                "session_id": "abc",
                "state": "running",
                "trial_billed_seconds": 0,
                "checks_done": 25,
            },
        )
        raw = await redis.get("sniper:status:tok:discord")
        assert raw is not None
        data = json.loads(raw)
        assert data["trial_billed_seconds"] == 40
        assert data["checks_done"] == 25

    asyncio.run(run())
