from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from pathlib import Path


def _safe_token(token: str) -> str:
    return "".join(c for c in token if c.isalnum() or c in "-_")


def names_file_path(data_dir: str, token: str) -> Path:
    return Path(data_dir) / _safe_token(token) / "names_to_check.txt"


def count_names_file(data_dir: str, token: str) -> int:
    path = names_file_path(data_dir, token)
    if not path.is_file():
        return 0
    total = 0
    with path.open(encoding="utf-8", errors="ignore") as handle:
        for line in handle:
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                total += 1
    return total


def read_names_from_file(data_dir: str, token: str) -> list[str]:
    path = names_file_path(data_dir, token)
    if not path.is_file():
        return []
    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    return [line.strip() for line in lines if line.strip() and not line.strip().startswith("#")]


class NameStream(ABC):
    @abstractmethod
    async def next_name(self) -> str | None:
        raise NotImplementedError

    @abstractmethod
    def position(self) -> int:
        """How many valid names have been consumed (used for resume offset)."""
        raise NotImplementedError


class FileNameStream(NameStream):
    """Stream names from disk — safe for multi-million line lists."""

    def __init__(self, path: Path, skip: int = 0):
        self.path = path
        self._skip = max(0, skip)
        self._consumed = 0
        self._lock = asyncio.Lock()
        self._fp = None
        self._exhausted = False

    def _ensure_open(self) -> None:
        if self._fp is not None or self._exhausted:
            return
        if not self.path.is_file():
            self._exhausted = True
            return
        self._fp = self.path.open(encoding="utf-8", errors="ignore")
        skipped = 0
        while skipped < self._skip:
            raw = self._fp.readline()
            if not raw:
                self._exhausted = True
                self._fp.close()
                self._fp = None
                return
            stripped = raw.strip()
            if stripped and not stripped.startswith("#"):
                skipped += 1

    def _next_sync(self) -> str | None:
        self._ensure_open()
        if self._exhausted or self._fp is None:
            return None
        while True:
            raw = self._fp.readline()
            if not raw:
                self._exhausted = True
                self._fp.close()
                self._fp = None
                return None
            name = raw.strip()
            if name and not name.startswith("#"):
                self._consumed += 1
                return name

    async def next_name(self) -> str | None:
        async with self._lock:
            return await asyncio.to_thread(self._next_sync)

    def position(self) -> int:
        return self._skip + self._consumed


class ListNameStream(NameStream):
    def __init__(self, names: list[str], offset: int = 0):
        self._names = names
        self._index = max(0, offset)

    async def next_name(self) -> str | None:
        if self._index >= len(self._names):
            return None
        name = self._names[self._index]
        self._index += 1
        return name

    def position(self) -> int:
        return self._index


def open_name_stream(job: dict, data_dir: str) -> tuple[NameStream | None, int]:
    """Return a stream + total count without loading huge lists into memory."""
    token = (job.get("token") or "").strip()
    offset = int(job.get("offset") or 0)

    if token and data_dir:
        path = names_file_path(data_dir, token)
        if path.is_file():
            total = count_names_file(data_dir, token)
            if total > 0:
                return FileNameStream(path, skip=offset), total

    names = [n.strip() for n in (job.get("names") or []) if n.strip()]
    if not names:
        return None, 0
    if offset >= len(names):
        return ListNameStream(names, offset=len(names)), len(names)
    return ListNameStream(names, offset=offset), len(names)


def resolve_names(job: dict, data_dir: str) -> list[str]:
    """Legacy helper for tests — do not use for large production jobs."""
    token = (job.get("token") or "").strip()
    if token and data_dir:
        from_file = read_names_from_file(data_dir, token)
        if from_file:
            return from_file
    return [n.strip() for n in (job.get("names") or []) if n.strip()]
