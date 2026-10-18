from __future__ import annotations

import json
from typing import Any

import requests

from sniper.turbo_engine import CheckResult, Status

# (connect, read) seconds — requests timeout tuple
REQUEST_TIMEOUT = (3, 6)

BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)

BROWSER_HEADERS = {
    "User-Agent": BROWSER_UA,
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "application/json, text/plain, */*",
}

BLOCKED_MARKERS = (
    "captcha-delivery.com",
    "just a moment",
    "cf_challenge",
    "hcaptcha.com",
    "challenge-platform",
)


def proxy_late(platform: str, name: str, detail: str) -> CheckResult:
    return CheckResult(name, platform, Status.PROXY_LATE, detail)


def is_rate_limited(status: int, body: str = "") -> bool:
    if status in (429, 503):
        return True
    if status in (401, 403):
        lower = body.lower()
        if any(m in lower for m in BLOCKED_MARKERS):
            return True
        if "rate limit" in lower:
            return True
    return False


def is_proxy_http(status: int) -> bool:
    return status in (403, 502, 503, 504)


def read_json_text(body: str) -> dict[str, Any] | None:
    try:
        data = json.loads(body)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        return None


REQUEST_ERRORS = (
    requests.Timeout,
    requests.ConnectionError,
    requests.RequestException,
)
