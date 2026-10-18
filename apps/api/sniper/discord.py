"""
DISCORD SNIPER — KEEP THIS SIMPLE.
Do NOT add: sleep, pacing, cooldowns, retry_after waits, POST endpoint.
GET username-suggestions-unauthed only.
"""

from __future__ import annotations

import asyncio

import aiohttp

from sniper.types import CheckResult, Status

URL = "https://discord.com/api/v9/unique-username/username-suggestions-unauthed"
HEADERS = {
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

# Back-compat for proxy_probe / older imports
SUGGESTIONS_URL = URL
DISCORD_HEADERS = HEADERS

_PROXY_SOFT_EXC = (
    asyncio.TimeoutError,
    TimeoutError,
    aiohttp.ClientConnectionError,
    aiohttp.ClientProxyConnectionError,
    aiohttp.ServerDisconnectedError,
    aiohttp.ClientOSError,
    aiohttp.ClientPayloadError,
)


def _proxy_auth_or_exhausted(detail: str) -> bool:
    d = detail.lower()
    return (
        "407" in d
        or "proxy authentication" in d
        or "traffic_exhausted" in d
        or "payment required" in d
    )


class DiscordChecker:
    platform = "discord"

    async def check(
        self,
        session: aiohttp.ClientSession,
        target: str,
        proxy_url: str,
    ) -> CheckResult:
        name = target.strip().lower()
        timeout = aiohttp.ClientTimeout(total=4.0, connect=1.5)
        try:
            async with session.get(
                URL,
                params={"global_name": name},
                headers=HEADERS,
                proxy=proxy_url,
                timeout=timeout,
            ) as r:
                if r.status == 429:
                    ra = (r.headers.get("Retry-After") or "").strip()
                    detail = f"retry_after={ra}" if ra else "429"
                    return CheckResult(name, self.platform, Status.RATE_LIMITED, detail)
                if r.status == 403:
                    body = await r.text()
                    return CheckResult(name, self.platform, Status.BLOCKED, body[:120])
                if r.status in (502, 503, 504):
                    return CheckResult(
                        name, self.platform, Status.PROXY_LATE, f"HTTP {r.status}"
                    )
                if r.status != 200:
                    return CheckResult(
                        name, self.platform, Status.ERROR, f"HTTP {r.status}"
                    )
                data = await r.json(content_type=None)
                suggested = str((data or {}).get("username") or "").strip().lower()
                if suggested == name:
                    return CheckResult(name, self.platform, Status.AVAILABLE)
                return CheckResult(
                    name, self.platform, Status.TAKEN, f"suggested={suggested}"
                )
        except aiohttp.ClientHttpProxyError as exc:
            detail = (str(exc).strip() or type(exc).__name__)[:120]
            if _proxy_auth_or_exhausted(detail):
                return CheckResult(name, self.platform, Status.ERROR, "proxy_auth")
            return CheckResult(name, self.platform, Status.PROXY_LATE, detail)
        except _PROXY_SOFT_EXC as exc:
            detail = (str(exc).strip() or type(exc).__name__)[:120]
            if _proxy_auth_or_exhausted(detail):
                return CheckResult(name, self.platform, Status.ERROR, "proxy_auth")
            return CheckResult(name, self.platform, Status.PROXY_LATE, detail)
        except Exception as exc:
            detail = (str(exc).strip() or type(exc).__name__)[:120]
            lowered = detail.lower()
            if _proxy_auth_or_exhausted(detail):
                return CheckResult(name, self.platform, Status.ERROR, "proxy_auth")
            if any(
                w in lowered
                for w in (
                    "timeout",
                    "disconnected",
                    "cannot connect",
                    "proxy",
                    "ssl",
                    "connection",
                )
            ):
                return CheckResult(name, self.platform, Status.PROXY_LATE, detail)
            return CheckResult(name, self.platform, Status.ERROR, detail)
