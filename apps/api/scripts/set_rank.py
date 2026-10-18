"""Set a user's rank by username. Run inside the API container with DATABASE_URL configured."""

from __future__ import annotations

import asyncio
import sys

from database import SessionLocal
from services.auth import update_user_rank


async def set_rank(username: str, rank: str) -> None:
    async with SessionLocal() as db:
        await update_user_rank(db, username, rank)
        print(f"Rank updated for user {username}: {rank}")


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("Usage: python -m scripts.set_rank <username> <rank>")
    asyncio.run(set_rank(sys.argv[1], sys.argv[2]))


if __name__ == "__main__":
    main()
