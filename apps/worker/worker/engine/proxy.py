from __future__ import annotations

import re

import httpx


def unique_proxy_lines(lines: list[str]) -> list[str]:
    """Dedupe proxy lines — 10 identical lines = 1 line = 50 workers, not 500."""
    seen: set[str] = set()
    unique: list[str] = []
    for raw in lines:
        line = raw.strip()
        if not line or line in seen:
            continue
        seen.add(line)
        unique.append(line)
    return unique


def proxy_line_to_url(line: str) -> str | None:
    """Convert common proxy line formats to an httpx-compatible proxy URL."""
    if not line:
        return None

    line = line.strip()
    if line.lower().startswith(("http://", "https://", "socks5://", "socks4://")):
        return line

    # user:pass@host:port
    if "@" in line:
        return f"http://{line}" if not line.startswith("http") else line

    parts = line.split(":")
    if len(parts) == 2:
        host, port = parts
        return f"http://{host}:{port}"
    if len(parts) >= 4:
        host = parts[0]
        port = parts[1]
        user = parts[2]
        password = ":".join(parts[3:])
        return f"http://{user}:{password}@{host}:{port}"

    return f"http://{line}"


def worker_count(proxy_lines: list[str], workers_per_line: int) -> int:
    unique = select_proxy_lines(proxy_lines, 10_000)
    if unique == [""]:
        return workers_per_line
    return len(unique) * workers_per_line


def select_proxy_lines(lines: list[str], max_lines: int) -> list[str]:
    """Dedupe proxies and cap how many lines we spin up (prevents FD exhaustion)."""
    unique = unique_proxy_lines(lines)
    if not unique:
        return [""]
    if len(unique) <= max_lines:
        return unique
    step = len(unique) / max_lines
    return [unique[int(i * step)] for i in range(max_lines)]


def _valid_proxy_url(url: str | None) -> bool:
    if not url:
        return True
    try:
        httpx.URL(url)
        return True
    except httpx.InvalidURL:
        return False


def build_proxy_urls(
    lines: list[str],
    max_lines: int,
    *,
    include_direct_fallback: bool = True,
) -> list[str | None]:
    """Validated proxy URLs; optional direct (no-proxy) fallback."""
    urls: list[str | None] = []
    for line in select_proxy_lines(lines, max_lines):
        if not line:
            continue
        url = proxy_line_to_url(line)
        if url and _valid_proxy_url(url):
            urls.append(url)
    if include_direct_fallback:
        urls.append(None)
    return urls if urls else [None]
