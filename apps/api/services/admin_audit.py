"""Append-only admin audit trail. No update/delete helpers on purpose."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from database import AdminAuditLog, User


async def record_admin_action(
    db: AsyncSession,
    *,
    actor: User,
    action: str,
    target_user_id: int | None = None,
    target_username: str | None = None,
    detail: str | None = None,
    meta: dict[str, Any] | None = None,
    actor_ip: str | None = None,
    commit: bool = True,
) -> AdminAuditLog:
    row = AdminAuditLog(
        actor_id=actor.id,
        actor_username=actor.username,
        action=action,
        target_user_id=target_user_id,
        target_username=target_username,
        detail=(detail or "")[:2000] or None,
        meta=meta,
        actor_ip=actor_ip,
    )
    db.add(row)
    if commit:
        await db.commit()
        await db.refresh(row)
    return row


def audit_row(row: AdminAuditLog) -> dict[str, Any]:
    return {
        "id": row.id,
        "actor_id": row.actor_id,
        "actor_username": row.actor_username,
        "action": row.action,
        "target_user_id": row.target_user_id,
        "target_username": row.target_username,
        "detail": row.detail,
        "meta": row.meta or {},
        "actor_ip": row.actor_ip,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }
