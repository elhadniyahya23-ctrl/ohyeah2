from fastapi import APIRouter
from sqlalchemy import text

from database import engine

router = APIRouter()


@router.get("/health")
async def health():
    return {"status": "ok", "service": "api"}


@router.get("/health/db")
async def health_db():
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    return {"status": "ok"}
