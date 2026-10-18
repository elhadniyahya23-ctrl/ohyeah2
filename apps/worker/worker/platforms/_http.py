from __future__ import annotations

import random
from typing import Any

import httpx

BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

USER_AGENTS = [
    BROWSER_UA,
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) "
        "Gecko/20100101 Firefox/125.0"
    ),
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) "
        "Version/17.4 Safari/605.1.15"
    ),
]

BROWSER_HEADERS = {
    "User-Agent": BROWSER_UA,
    "Accept-Language": "en-US,en;q=0.9",
}

BLOCKED_MARKERS = (
    "captcha-delivery.com",
    "geo.captcha",
    "just a moment",
    "cf_challenge",
    "hcaptcha.com",
    "challenge-platform",
    "please enable js",
)


def random_user_agent() -> str:
    return random.choice(USER_AGENTS)


def browser_headers(*, referer: str | None = None, origin: str | None = None) -> dict[str, str]:
    headers = {
        "User-Agent": random_user_agent(),
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }
    if referer:
        headers["Referer"] = referer
    if origin:
        headers["Origin"] = origin
    return headers


def is_blocked_response(resp: httpx.Response) -> bool:
    if resp.status_code in (429, 503):
        return True
    if resp.status_code == 403:
        return True

    body = resp.text.lower()
    if any(marker in body for marker in BLOCKED_MARKERS):
        return True

    content_type = resp.headers.get("content-type", "").lower()
    if resp.status_code == 403 and "text/html" in content_type:
        return True

    try:
        data = resp.json()
    except Exception:
        return False

    if not isinstance(data, dict):
        return False

    url = str(data.get("url", "")).lower()
    return "captcha" in url


def parse_retry_after(status_code: int, body: str, headers: dict[str, str] | None = None) -> float | None:
    if headers:
        raw = headers.get("Retry-After") or headers.get("retry-after")
        if raw:
            try:
                return max(0.5, float(raw))
            except ValueError:
                pass
    try:
        import json

        data = json.loads(body)
    except Exception:
        return None
    if isinstance(data, dict) and data.get("retry_after") is not None:
        try:
            return max(0.5, float(data["retry_after"]))
        except (TypeError, ValueError):
            return None
    return None


def response_indicates_rate_limit(status_code: int, body: str = "") -> bool:
    if status_code in (429, 503):
        return True
    if status_code in (401, 403):
        lower = body.lower()
        if any(marker in lower for marker in BLOCKED_MARKERS):
            return True
        if "<html" in lower:
            return True
        try:
            import json

            data = json.loads(body)
        except Exception:
            return status_code == 403
        if isinstance(data, dict):
            message = str(data.get("message", "")).lower()
            if "rate limit" in message or data.get("retry_after") is not None:
                return True
            if status_code == 403:
                return True
    return False
