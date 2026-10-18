"""Ensure only allowlisted usernames are Admin; demote everyone else with Admin rank."""

from __future__ import annotations

import asyncio

from sqlalchemy import select

from database import SessionLocal, User
from services.plans import ADMIN_OWNER_TOKENS, ADMIN_USERNAMES


async def sync_admins() -> None:
    async with SessionLocal() as db:
        # Promote allowlisted accounts
        for username in sorted(ADMIN_USERNAMES):
            result = await db.execute(select(User).where(User.username == username))
            user = result.scalar_one_or_none()
            if not user:
                print(f"WARN: allowlisted admin '{username}' not found")
                continue
            if (user.rank or "").lower() != "admin":
                user.rank = "Admin"
                user.plan_expires_at = None
                print(f"Promoted {username} -> Admin")
            else:
                print(f"OK {username} already Admin")

        # Promote owner-token accounts
        for token in sorted(ADMIN_OWNER_TOKENS):
            result = await db.execute(select(User).where(User.token == token))
            user = result.scalar_one_or_none()
            if not user:
                print(f"WARN: owner token '{token[:12]}…' not found")
                continue
            if (user.rank or "").lower() != "admin":
                user.rank = "Admin"
                user.plan_expires_at = None
                print(f"Promoted owner {user.username} (token {token[:12]}…) -> Admin")
            else:
                print(f"OK owner {user.username} already Admin")

        # Demote anyone else currently marked Admin
        result = await db.execute(select(User).where(User.rank.ilike("admin")))
        for user in result.scalars().all():
            if (user.username or "").lower() in ADMIN_USERNAMES:
                continue
            if (user.token or "").strip() in ADMIN_OWNER_TOKENS:
                continue
            user.rank = "Free Trial"
            user.trial_used_seconds = user.trial_used_seconds or 0
            print(f"Demoted {user.username} -> Free Trial (not allowlisted)")

        await db.commit()
        print(
            "Admin sync complete. Usernames:",
            ", ".join(sorted(ADMIN_USERNAMES)),
            "| owner tokens:",
            len(ADMIN_OWNER_TOKENS),
        )


def main() -> None:
    asyncio.run(sync_admins())


if __name__ == "__main__":
    main()
