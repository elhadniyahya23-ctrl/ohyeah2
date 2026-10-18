"""Shared requests helpers for turbo checkers (thread-local sessions)."""

from __future__ import annotations

import threading

import requests
from requests.adapters import HTTPAdapter

_local = threading.local()


def get_session() -> requests.Session:
    sess = getattr(_local, "session", None)
    if sess is None:
        sess = requests.Session()
        # Large pools — Discord turbo runs dozens of concurrent workers per process.
        adapter = HTTPAdapter(pool_connections=160, pool_maxsize=160, max_retries=0)
        sess.mount("http://", adapter)
        sess.mount("https://", adapter)
        _local.session = sess
    return sess


def proxy_dict(proxy_url: str | None) -> dict[str, str] | None:
    # Empty/None = direct egress (datacenter IP mode) — no proxy env picked up.
    if not proxy_url:
        return None
    return {"http": proxy_url, "https": proxy_url}
