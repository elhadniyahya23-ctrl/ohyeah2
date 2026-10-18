"""Set a user's password by username. Run inside the API container with DATABASE_URL configured."""

from __future__ import annotations

import asyncio
import sys

from database import SessionLocal
from services.auth import update_user_password


async def set_password(username: str, password: str) -> None:
    async with SessionLocal() as db:
        await update_user_password(db, username, password)
        print(f"Password updated for user: {username}")


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("Usage: python -m scripts.set_password <username> <password>")
    asyncio.run(set_password(sys.argv[1], sys.argv[2]))


if __name__ == "__main__":
    main()
