from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from worker.main import JobRunner


@pytest.mark.asyncio
async def test_run_job_clears_stop_event_before_next_job():
    redis = MagicMock()
    runner = JobRunner(redis)
    runner._stop.set()

    with patch.object(runner._engine, "run", new_callable=AsyncMock) as mock_run, patch.object(
        runner._engine, "update_status", new_callable=AsyncMock
    ) as mock_status:
        await runner.run_job({"platform": "discord", "names": ["alpha"], "total_names": 1})

    assert not runner._stop.is_set()
    mock_status.assert_awaited()
    assert mock_status.await_args_list[0].args[3] == "running"
    mock_run.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_job_skips_unknown_platform():
    redis = MagicMock()
    runner = JobRunner(redis)

    with patch.object(runner._engine, "run", new_callable=AsyncMock) as mock_run, patch.object(
        runner._engine, "update_status", new_callable=AsyncMock
    ) as mock_status:
        await runner.run_job({"platform": "unknown-platform", "names": ["alpha"]})

    mock_run.assert_not_awaited()
    mock_status.assert_awaited_once()
