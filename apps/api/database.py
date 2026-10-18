from collections.abc import AsyncGenerator
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB as PostgresJSONB
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.pool import NullPool

from config import settings

JSONType = JSON().with_variant(PostgresJSONB, "postgresql")


def _engine_connect_args() -> dict:
    if settings.async_database_url.startswith("sqlite"):
        return {"check_same_thread": False}
    # Bound waits so nginx (30s) is not the first timeout clients hit.
    args: dict = {"timeout": 20, "command_timeout": 25}
    if settings.ssl_required:
        args["ssl"] = "require"
    return args


def _engine_kwargs() -> dict:
    """Keep Neon connection count low across many sniper replicas."""
    if settings.async_database_url.startswith("sqlite"):
        return {
            "connect_args": _engine_connect_args(),
        }
    mode = (settings.api_mode or "control").strip().lower()
    if mode == "sniper":
        # One job per node — no need for a warm pool. NullPool = connect per checkout.
        return {
            "poolclass": NullPool,
            "connect_args": _engine_connect_args(),
        }
    return {
        "pool_pre_ping": True,
        "pool_size": 3,
        "max_overflow": 2,
        "pool_timeout": 8,
        "pool_recycle": 280,
        "connect_args": _engine_connect_args(),
    }


engine = create_async_engine(settings.async_database_url, **_engine_kwargs())
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    __table_args__ = (Index("ix_users_token", "token"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    token: Mapped[str | None] = mapped_column(String, nullable=True)
    plan_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    trial_used_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rank: Mapped[str | None] = mapped_column(String, nullable=True)
    registration_ip: Mapped[str | None] = mapped_column(String, nullable=True)
    last_ip: Mapped[str | None] = mapped_column(String, nullable=True)
    registration_ip_plain: Mapped[str | None] = mapped_column(String, nullable=True)


class SniperJob(Base):
    __tablename__ = "sniper_jobs"
    __table_args__ = (Index("ix_sniper_jobs_user_token", "user_token"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    user_token: Mapped[str] = mapped_column(String, nullable=False)
    platform: Mapped[str] = mapped_column(String(32), nullable=False, default="discord")
    targets: Mapped[list] = mapped_column(JSONType, nullable=False)
    proxy: Mapped[str] = mapped_column(Text, nullable=False)
    webhook_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    workers: Mapped[int] = mapped_column(Integer, nullable=False, default=160)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="idle")
    stats: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class SniperHit(Base):
    __tablename__ = "sniper_hits"
    __table_args__ = (Index("ix_sniper_hits_job_id", "job_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(String(36), ForeignKey("sniper_jobs.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    target: Mapped[str] = mapped_column(String(256), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PaymentOrder(Base):
    __tablename__ = "payment_orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    plan_id: Mapped[str] = mapped_column(String(64), nullable=False)
    method: Mapped[str] = mapped_column(String(32), nullable=False)  # paypal | crypto
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    amount_usd: Mapped[str] = mapped_column(String(32), nullable=False)
    currency: Mapped[str | None] = mapped_column(String(16), nullable=True)
    tx_hash: Mapped[str | None] = mapped_column(String(256), nullable=True)
    sender_wallet: Mapped[str | None] = mapped_column(String(256), nullable=True)
    paypal_order_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AdminAuditLog(Base):
    """Append-only admin action log — readable by all admins, never edited/deleted via API."""

    __tablename__ = "admin_audit_logs"
    __table_args__ = (
        Index("ix_admin_audit_logs_created_at", "created_at"),
        Index("ix_admin_audit_logs_actor_id", "actor_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    actor_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    actor_username: Mapped[str] = mapped_column(String(64), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    target_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    target_username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    meta: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    actor_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session
