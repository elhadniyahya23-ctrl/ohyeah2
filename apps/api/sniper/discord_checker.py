"""
Discord checker — GET suggestions endpoint ONLY.

Never use POST /username-attempt-unauthed on the hot path: it rate-limits far
harder than suggestions and tanks CPS (especially on 4C lists with many
suggestion matches).
"""

from __future__ import annotations

import json
import re

import requests

from sniper.checkers.common import REQUEST_ERRORS, proxy_late
from sniper.http_util import get_session, proxy_dict
from sniper.turbo_engine import CheckResult, Status

SUGGESTIONS_URL = (
    "https://discord.com/api/v9/unique-username/username-suggestions-unauthed"
)

DISCORD_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Origin": "https://discord.com",
    "Referer": "https://discord.com/register",
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "X-Discord-Locale": "en-US",
}

# Fail slow exits faster so workers are not stuck in long timeouts.
DISCORD_TIMEOUT = (1.2, 2.6)

# Discord pomelo usernames: 2–32 of a-z, 0-9, underscore, period.
_USERNAME_RE = re.compile(r"^[a-z0-9._]{2,32}$")


def _retry_pause(resp: requests.Response, default: float = 0.35) -> float:
    """Honor Discord Retry-After from headers or JSON body (capped)."""
    retry_after = (
        resp.headers.get("Retry-After")
        or resp.headers.get("retry-after")
        or resp.headers.get("X-RateLimit-Reset-After")
        or resp.headers.get("x-ratelimit-reset-after")
    )
    if not retry_after:
        try:
            data = resp.json()
            if isinstance(data, dict) and data.get("retry_after") is not None:
                retry_after = data.get("retry_after")
        except (json.JSONDecodeError, ValueError, TypeError):
            pass
    pause = default
    if retry_after is not None:
        try:
            # Cap high but honor real backoff — resubmitting early = 429 storm.
            pause = max(0.15, min(float(retry_after), 12.0))
        except (TypeError, ValueError):
            pass
    return pause


def _rate_limited(name: str, platform: str, resp: requests.Response) -> CheckResult:
    pause = _retry_pause(resp)
    return CheckResult(name, platform, Status.RATE_LIMITED, f"retry_after={pause}")


class DiscordChecker:
    platform = "discord"

    def check(self, target: str, proxy_url: str) -> CheckResult:
        name = target.strip().lower()
        if not _USERNAME_RE.match(name):
            return CheckResult(name, self.platform, Status.TAKEN, "invalid_format")

        try:
            resp = get_session().get(
                SUGGESTIONS_URL,
                params={"global_name": name},
                headers=DISCORD_HEADERS,
                proxies=proxy_dict(proxy_url),
                timeout=DISCORD_TIMEOUT,
            )
            if resp.status_code == 429:
                return _rate_limited(name, self.platform, resp)
            if resp.status_code in (403, 407, 502, 503, 504):
                return proxy_late(self.platform, name, f"http_{resp.status_code}")
            if resp.status_code != 200:
                return CheckResult(
                    name,
                    self.platform,
                    Status.ERROR,
                    f"HTTP {resp.status_code}: {resp.text[:80]}",
                )
            try:
                data = resp.json()
            except (json.JSONDecodeError, ValueError):
                return proxy_late(self.platform, name, "bad_json")
            if not isinstance(data, dict):
                return proxy_late(self.platform, name, "bad_json")
            if data.get("retry_after") is not None:
                pause = _retry_pause(resp)
                return CheckResult(
                    name, self.platform, Status.RATE_LIMITED, f"retry_after={pause}"
                )
            suggested = str(data.get("username") or "").strip().lower()
        except requests.Timeout:
            return proxy_late(self.platform, name, "timeout")
        except REQUEST_ERRORS as exc:
            return proxy_late(self.platform, name, str(exc)[:80])

        if not suggested:
            return proxy_late(self.platform, name, "empty_suggestion")
        if suggested == name:
            return CheckResult(name, self.platform, Status.AVAILABLE)
        return CheckResult(name, self.platform, Status.TAKEN, f"suggested={suggested}")
