"""Guns.lol username checker (aiohttp)."""

from __future__ import annotations

import asyncio
import re

import aiohttp

from sniper.types import CheckResult, Status

DEFAULT_TITLE = "guns.lol: Everything you want, right here."
DEFAULT_TITLE_TR = "guns.lol: İstediğin her şey, burada."
NOT_FOUND_FRAGMENTS = ("username not found", "bulunamad")
_CHALLENGE_MARKERS = (
    "captcha",
    "cf-challenge",
    "just a moment",
    "access denied",
    "verify you are human",
)
_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


def classify_guns_html(name: str, body: str) -> CheckResult:
    platform = "guns"
    lower = body.lower()
    if any(marker in lower for marker in _CHALLENGE_MARKERS):
        return CheckResult(name, platform, Status.PROXY_LATE, "challenge")

    title_match = re.search(r"<title>([^<]+)</title>", body, re.IGNORECASE)
    if not title_match:
        return CheckResult(name, platform, Status.PROXY_LATE, "no_title")

    title_l = title_match.group(1).strip().lower()
    needle = name.strip().lstrip("@").lower()
    if re.match(rf"^@{re.escape(needle)}\s*\|\s*guns\.lol$", title_l):
        return CheckResult(name, platform, Status.TAKEN, "title")
    if re.search(r"^@\S+\s*\|\s*guns\.lol$", title_l):
        return CheckResult(name, platform, Status.TAKEN, "title_profile")

    is_default = title_l in {DEFAULT_TITLE.lower(), DEFAULT_TITLE_TR.lower()}
    has_not_found = any(fragment in lower for fragment in NOT_FOUND_FRAGMENTS)
    if is_default and has_not_found:
        return CheckResult(name, platform, Status.AVAILABLE, "not_found")
    if is_default:
        return CheckResult(name, platform, Status.PROXY_LATE, "default_title_only")
    return CheckResult(name, platform, Status.PROXY_LATE, "ambiguous")


class GunsChecker:
    platform = "guns"

    async def check(
        self,
        session: aiohttp.ClientSession,
        target: str,
        proxy_url: str,
    ) -> CheckResult:
        name = target.strip().lstrip("@")
        headers = {
            **_BROWSER_HEADERS,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Referer": "https://guns.lol/",
        }
        timeout = aiohttp.ClientTimeout(total=8, connect=3)
        try:
            async with session.get(
                f"https://guns.lol/{name}",
                headers=headers,
                proxy=proxy_url,
                timeout=timeout,
                allow_redirects=True,
            ) as resp:
                body = await resp.text()
                if resp.status == 429:
                    ra = (resp.headers.get("Retry-After") or "").strip()
                    detail = "retry_after=0.45"
                    if ra:
                        try:
                            detail = f"retry_after={min(float(ra), 2.0)}"
                        except ValueError:
                            pass
                    return CheckResult(name, self.platform, Status.RATE_LIMITED, detail)
                if resp.status in (502, 503, 504):
                    return CheckResult(
                        name, self.platform, Status.PROXY_LATE, f"HTTP {resp.status}"
                    )
                if resp.status not in (200, 404):
                    return CheckResult(
                        name, self.platform, Status.PROXY_LATE, f"http_{resp.status}"
                    )
                return classify_guns_html(name, body)
        except aiohttp.TooManyRedirects:
            return CheckResult(name, self.platform, Status.PROXY_LATE, "redirect_loop")
        except (asyncio.TimeoutError, TimeoutError, aiohttp.ClientError) as exc:
            detail = (str(exc).strip() or type(exc).__name__)[:120]
            lowered = detail.lower()
            if "redirect" in lowered or "too many" in lowered:
                return CheckResult(name, self.platform, Status.PROXY_LATE, "redirect_loop")
            return CheckResult(name, self.platform, Status.PROXY_LATE, detail)
        except Exception as exc:
            return CheckResult(name, self.platform, Status.ERROR, str(exc)[:120])
