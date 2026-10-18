from __future__ import annotations

import json
import time

import requests

from sniper.checkers.common import REQUEST_ERRORS, REQUEST_TIMEOUT, is_rate_limited, proxy_late
from sniper.http_util import get_session, proxy_dict
from sniper.turbo_engine import CheckResult, Status

ROBLOX_URL = "https://auth.roblox.com/v1/usernames/validate"
ROBLOX_BODY = {"birthday": "2000-01-01T07:00:00.000Z"}
CSRF_TTL_SEC = 300

ROBLOX_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Content-Type": "application/json",
    "Origin": "https://www.roblox.com",
    "Referer": "https://www.roblox.com/",
}


def _parse_roblox_body(name: str, status: int, body: str) -> CheckResult:
    if status == 429:
        return CheckResult(name, "roblox", Status.RATE_LIMITED, "rate_limit")
    if status in (502, 503, 504):
        return proxy_late("roblox", name, f"http_{status}")
    if status != 200:
        return CheckResult(name, "roblox", Status.ERROR, f"http_{status}")
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return proxy_late("roblox", name, "bad_json")
    code = data.get("code")
    if code == 0:
        return CheckResult(name, "roblox", Status.AVAILABLE)
    if code in (1, 2, 3, 4, 10, 11, 12):
        return CheckResult(name, "roblox", Status.TAKEN, f"code_{code}")
    return CheckResult(name, "roblox", Status.ERROR, f"code_{code}")


class RobloxChecker:
    platform = "roblox"

    def __init__(self) -> None:
        self._csrf_cache: dict[str, tuple[str, float]] = {}

    def _cached_csrf(self, proxy_url: str) -> str | None:
        entry = self._csrf_cache.get(proxy_url)
        if not entry:
            return None
        token, expires_at = entry
        if time.monotonic() >= expires_at:
            self._csrf_cache.pop(proxy_url, None)
            return None
        return token

    def _store_csrf(self, proxy_url: str, token: str) -> None:
        self._csrf_cache[proxy_url] = (token, time.monotonic() + CSRF_TTL_SEC)

    def _post_validate(
        self,
        name: str,
        proxy_url: str,
        *,
        csrf: str | None,
    ) -> tuple[int, str, str | None]:
        headers = dict(ROBLOX_HEADERS)
        if csrf:
            headers["X-CSRF-TOKEN"] = csrf
        resp = get_session().post(
            ROBLOX_URL,
            json={"username": name, **ROBLOX_BODY},
            headers=headers,
            proxies=proxy_dict(proxy_url),
            timeout=REQUEST_TIMEOUT,
        )
        next_csrf = resp.headers.get("x-csrf-token")
        return resp.status_code, resp.text, next_csrf

    def check(self, target: str, proxy_url: str) -> CheckResult:
        name = target.strip()
        try:
            csrf = self._cached_csrf(proxy_url)
            status, body, next_csrf = self._post_validate(name, proxy_url, csrf=csrf)

            if is_rate_limited(status, body):
                return CheckResult(name, self.platform, Status.RATE_LIMITED, "rate_limit")

            if status == 403 and next_csrf:
                self._store_csrf(proxy_url, next_csrf)
                status, body, _ = self._post_validate(name, proxy_url, csrf=next_csrf)
                if is_rate_limited(status, body):
                    return CheckResult(name, self.platform, Status.RATE_LIMITED, "rate_limit")

            if status == 403:
                return proxy_late(self.platform, name, "blocked_403")

            return _parse_roblox_body(name, status, body)
        except requests.Timeout:
            return proxy_late(self.platform, name, "timeout")
        except REQUEST_ERRORS as exc:
            return proxy_late(self.platform, name, str(exc)[:80])
