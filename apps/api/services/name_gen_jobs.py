from __future__ import annotations

import asyncio
import threading
import time
import uuid
from collections.abc import Callable
from typing import Any

from services.name_generator import HEAVY_TYPES

_jobs: dict[str, dict[str, Any]] = {}
_lock = threading.Lock()
_TTL_SEC = 3600
_MAX_JOBS_PER_USER = 3


def is_heavy_generator(gen_type: str) -> bool:
    return gen_type.strip().upper() in HEAVY_TYPES


def _prune_old() -> None:
    now = time.time()
    with _lock:
        stale = [jid for jid, j in _jobs.items() if now - float(j.get("created_at", 0)) > _TTL_SEC]
        for jid in stale:
            _jobs.pop(jid, None)


def _active_jobs_for(owner_token: str) -> int:
    return sum(
        1
        for job in _jobs.values()
        if job.get("owner_token") == owner_token and job.get("status") in {"pending", "running"}
    )


def create_job(gen_type: str, owner_token: str) -> str:
    _prune_old()
    with _lock:
        if _active_jobs_for(owner_token) >= _MAX_JOBS_PER_USER:
            raise RuntimeError("Too many generation jobs running. Wait for one to finish.")
        job_id = uuid.uuid4().hex[:16]
        _jobs[job_id] = {
            "id": job_id,
            "type": gen_type,
            "owner_token": owner_token,
            "status": "pending",
            "created_at": time.time(),
            "result": None,
            "error": None,
        }
        return job_id


def get_job(job_id: str, owner_token: str) -> dict[str, Any] | None:
    with _lock:
        job = _jobs.get(job_id)
        if not job or job.get("owner_token") != owner_token:
            return None
        return {k: v for k, v in job.items() if k != "owner_token"}


def _set_job(job_id: str, **fields: Any) -> None:
    with _lock:
        if job_id in _jobs:
            _jobs[job_id].update(fields)


async def run_job(job_id: str, fn: Callable[[], dict]) -> None:
    _set_job(job_id, status="running", started_at=time.time())
    try:
        result = await asyncio.to_thread(fn)
        _set_job(job_id, status="done", result=result, finished_at=time.time())
    except Exception as exc:
        _set_job(job_id, status="failed", error=str(exc)[:240], finished_at=time.time())
