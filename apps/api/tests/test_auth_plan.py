from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.auth import user_has_active_plan
from services.plans import (
    TRIAL_LIMIT_SECONDS,
    add_trial_seconds,
    is_admin,
    plan_payload,
    trial_exhausted,
    trial_remaining_seconds,
)


def test_user_has_active_plan_with_timezone_aware_expiry():
    user = SimpleNamespace(
        username="someone",
        plan_expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        rank="Premium",
        trial_used_seconds=0,
    )
    assert user_has_active_plan(user) is True


def test_user_has_active_plan_with_naive_expiry():
    user = SimpleNamespace(
        username="someone",
        plan_expires_at=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=30),
        rank="Premium",
        trial_used_seconds=0,
    )
    assert user_has_active_plan(user) is True


def test_user_has_active_plan_for_allowlisted_admin():
    user = SimpleNamespace(
        username="asiopitos",
        plan_expires_at=None,
        rank="Free Trial",
        trial_used_seconds=0,
    )
    assert is_admin(user) is True
    assert user_has_active_plan(user) is True


def test_admin_rank_alone_is_not_enough():
    user = SimpleNamespace(
        username="randomuser",
        plan_expires_at=None,
        rank="Admin",
        trial_used_seconds=0,
    )
    assert is_admin(user) is False
    assert user_has_active_plan(user) is False


def test_eya_is_admin():
    user = SimpleNamespace(username="eya", plan_expires_at=None, rank="Premium", trial_used_seconds=0)
    assert is_admin(user) is True


def test_free_trial_has_active_plan_with_time_left():
    user = SimpleNamespace(
        username="trialguy",
        plan_expires_at=None,
        rank="Free Trial",
        trial_used_seconds=60,
    )
    assert user_has_active_plan(user) is True
    assert trial_remaining_seconds(user) == TRIAL_LIMIT_SECONDS - 60
    assert trial_exhausted(user) is False


def test_free_trial_exhausted_blocks_plan():
    user = SimpleNamespace(
        username="trialguy",
        plan_expires_at=None,
        rank="Free Trial",
        trial_used_seconds=TRIAL_LIMIT_SECONDS,
    )
    assert user_has_active_plan(user) is False
    assert trial_exhausted(user) is True


def test_plan_payload_marks_expired_trial_rank():
    user = SimpleNamespace(
        username="trialguy",
        plan_expires_at=None,
        rank="Free Trial Expired",
        trial_used_seconds=TRIAL_LIMIT_SECONDS,
    )
    payload = plan_payload(user)
    assert payload["has_active_plan"] is False
    assert payload["trial_exhausted"] is True
    assert payload["is_admin"] is False


@pytest.mark.asyncio
async def test_add_trial_seconds_expires_at_limit():
    user = SimpleNamespace(
        username="trialguy",
        plan_expires_at=None,
        rank="Free Trial",
        trial_used_seconds=290,
    )
    db = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()

    updated = await add_trial_seconds(db, user, 20)
    assert updated.rank == "Free Trial Expired"
    assert updated.trial_used_seconds == TRIAL_LIMIT_SECONDS
    db.commit.assert_awaited()
