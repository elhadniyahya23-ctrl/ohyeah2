import asyncio
import time
from unittest.mock import AsyncMock

from services.trial_billing import session_elapsed


def test_session_is_stuck_queued():
    from routers.sniper import _session_is_stuck

    assert not _session_is_stuck({"state": "running", "checks_done": 0})
    assert not _session_is_stuck({"state": "queued", "checks_done": 5, "started_at": time.time()})
    assert not _session_is_stuck({"state": "queued", "checks_done": 0, "started_at": time.time()})
    stuck = {
        "state": "running",
        "checks_done": 0,
        "started_at": time.time() - 25,
    }
    assert _session_is_stuck(stuck)


def test_session_elapsed_queued_does_not_burn_trial():
    data = {"started_at": time.time() - 30, "state": "queued", "elapsed_seconds": 0}
    assert session_elapsed(data) == 0


def test_discord_never_overflows_onto_control_api():
    from services.sniper_dispatch import maybe_start_overflow_job

    redis = AsyncMock()
    stuck = {
        "state": "queued",
        "checks_done": 0,
        "started_at": time.time() - 60,
    }
    assert asyncio.run(maybe_start_overflow_job(redis, "tok", "discord", stuck)) is False
    redis.get.assert_not_called()


def test_recover_skips_waiting_discord(monkeypatch):
    from services import sniper_cleanup

    redis = AsyncMock()
    stuck = {
        "state": "queued",
        "checks_done": 0,
        "started_at": time.time() - 60,
    }

    async def fake_scan(_redis):
        return [("tok", "discord", stuck)]

    monkeypatch.setattr(sniper_cleanup, "scan_status_keys", fake_scan)
    assert asyncio.run(sniper_cleanup.recover_stuck_queued_sessions(redis)) == 0
