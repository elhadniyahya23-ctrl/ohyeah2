import asyncio

import pytest
from sqlalchemy import select
from sqlalchemy.exc import OperationalError

from database import SessionLocal, User
from scripts.set_password import set_password
from services.auth import verify_password


@pytest.mark.asyncio
async def test_set_password_updates_hash():
    try:
        async with SessionLocal() as db:
            result = await db.execute(select(User).where(User.username == "__test_set_password__"))
            user = result.scalar_one_or_none()
    except (OperationalError, OSError):
        pytest.skip("Database unavailable in CI")

    if user is None:
        pytest.skip("No test user in database")

    await set_password(user.username, "newpass123")
    async with SessionLocal() as db:
        result = await db.execute(select(User).where(User.username == user.username))
        updated = result.scalar_one()
        assert verify_password("newpass123", updated.password_hash)
