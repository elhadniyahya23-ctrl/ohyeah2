from __future__ import annotations

import asyncio
import fnmatch
import time
from collections import defaultdict
from typing import Any


class LocalRedis:
    """Small async Redis substitute for local development.

    It implements the subset used by the API so localhost can run without a
    Redis server. Data is process-local and intentionally disappears on restart.
    """

    def __init__(self) -> None:
        self._kv: dict[str, tuple[Any, float | None]] = {}
        self._lists: dict[str, list[Any]] = defaultdict(list)
        self._condition = asyncio.Condition()

    def _expired(self, expires_at: float | None) -> bool:
        return expires_at is not None and expires_at <= time.monotonic()

    def _cleanup_key(self, key: str) -> None:
        item = self._kv.get(key)
        if item and self._expired(item[1]):
            self._kv.pop(key, None)

    async def ping(self) -> bool:
        return True

    async def get(self, key: str) -> Any:
        self._cleanup_key(key)
        item = self._kv.get(key)
        return item[0] if item else None

    async def set(
        self,
        key: str,
        value: Any,
        *,
        ex: int | float | None = None,
        nx: bool = False,
        **_: Any,
    ) -> bool:
        self._cleanup_key(key)
        if nx and key in self._kv:
            return False
        expires_at = time.monotonic() + float(ex) if ex else None
        self._kv[key] = (value, expires_at)
        return True

    async def delete(self, *keys: str) -> int:
        removed = 0
        for key in keys:
            if key in self._kv:
                removed += 1
                self._kv.pop(key, None)
            if key in self._lists:
                removed += 1
                self._lists.pop(key, None)
        return removed

    async def scan(
        self,
        cursor: int | bytes = 0,
        *,
        match: str | None = None,
        count: int = 100,
    ) -> tuple[int, list[str]]:
        del cursor, count
        for key in list(self._kv):
            self._cleanup_key(key)
        keys = list(self._kv) + list(self._lists)
        if match:
            keys = [key for key in keys if fnmatch.fnmatch(key, match)]
        return 0, keys

    async def lpush(self, key: str, value: Any) -> int:
        async with self._condition:
            self._lists[key].insert(0, value)
            self._condition.notify_all()
            return len(self._lists[key])

    async def brpop(self, key: str, timeout: int = 0) -> tuple[str, Any] | None:
        deadline = time.monotonic() + timeout if timeout else None
        async with self._condition:
            while not self._lists.get(key):
                if deadline is None:
                    await self._condition.wait()
                    continue
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None
                try:
                    await asyncio.wait_for(self._condition.wait(), timeout=remaining)
                except asyncio.TimeoutError:
                    return None
            return key, self._lists[key].pop()

    async def llen(self, key: str) -> int:
        return len(self._lists.get(key, []))

    async def lrange(self, key: str, start: int, end: int) -> list[Any]:
        items = list(self._lists.get(key, []))
        if end == -1:
            return items[start:]
        return items[start : end + 1]

    async def lrem(self, key: str, count: int, value: Any) -> int:
        items = self._lists.get(key, [])
        if not items:
            return 0
        removed = 0
        kept: list[Any] = []
        limit = abs(count)
        iterable = reversed(items) if count < 0 else items
        for item in iterable:
            should_remove = item == value and (count == 0 or removed < limit)
            if should_remove:
                removed += 1
            else:
                kept.append(item)
        if count < 0:
            kept.reverse()
        self._lists[key] = kept
        return removed

    async def publish(self, channel: str, message: str) -> int:
        del channel, message
        return 0

    def pubsub(self) -> "_LocalPubSub":
        return _LocalPubSub()

    async def aclose(self) -> None:
        self._kv.clear()
        self._lists.clear()


class _LocalPubSub:
    async def subscribe(self, *_channels: str) -> None:
        return None

    async def get_message(
        self,
        *,
        ignore_subscribe_messages: bool = True,
        timeout: float | None = None,
    ) -> None:
        del ignore_subscribe_messages
        if timeout:
            await asyncio.sleep(timeout)
        return None

    async def close(self) -> None:
        return None
