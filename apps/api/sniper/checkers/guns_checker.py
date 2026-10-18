from __future__ import annotations

import re

import requests

from sniper.checkers.common import BROWSER_HEADERS, REQUEST_ERRORS, is_proxy_http, is_rate_limited, proxy_late
from sniper.http_util import get_session, proxy_dict
from sniper.turbo_engine import CheckResult, Status

GUNS_TIMEOUT = (3, 8)
# Exact marketing title on the empty-profile / not-found page (worker-validated).
DEFAULT_TITLE = "guns.lol: Everything you want, right here."
DEFAULT_TITLE_TR = "guns.lol: İstediğin her şey, burada."
# Must appear with the default title — alone these strings can show up elsewhere.
NOT_FOUND_FRAGMENTS = ("username not found", "bulunamad")
_CHALLENGE_MARKERS = (
    "captcha",
    "cf-challenge",
    "just a moment",
    "access denied",
    "verify you are human",
)


def classify_guns_html(name: str, body: str, *, status: int) -> CheckResult:
    """Classify guns.lol HTML.

    Proxies sometimes return the marketing homepage shell (default <title>) for
    blocked requests — never treat default title alone as available. Require an
    explicit not-found marker too. Never treat bare HTTP 404 as a capture.
    Soft blocks (challenge / homepage shell) rotate the exit as proxy_late so
    the job keeps CPS instead of storm-pausing into idle.
    """
    platform = "guns"
    lower = body.lower()

    if any(marker in lower for marker in _CHALLENGE_MARKERS):
        return proxy_late(platform, name, "challenge")

    title_match = re.search(r"<title>([^<]+)</title>", body, re.IGNORECASE)
    if not title_match:
        return proxy_late(platform, name, "no_title")

    title = title_match.group(1).strip()
    title_l = title.lower()
    needle = name.strip().lstrip("@").lower()

    # Taken profiles use "@handle | guns.lol".
    taken_title = re.match(
        rf"^@{re.escape(needle)}\s*\|\s*guns\.lol$", title_l, re.IGNORECASE
    )
    if taken_title:
        return CheckResult(name, platform, Status.TAKEN, "title")

    # Broader taken signal: "@something | guns.lol" (soft redirect to another profile).
    if re.search(r"^@\S+\s*\|\s*guns\.lol$", title_l):
        return CheckResult(name, platform, Status.TAKEN, "title_profile")

    is_default_title = title_l in {DEFAULT_TITLE.lower(), DEFAULT_TITLE_TR.lower()}
    has_not_found = any(fragment in lower for fragment in NOT_FOUND_FRAGMENTS)

    # Free handle: marketing title + explicit not-found copy. Both required.
    if is_default_title and has_not_found:
        return CheckResult(name, platform, Status.AVAILABLE, "not_found")

    # Default title without not-found = soft proxy block — rotate exit, don't ERROR.
    if is_default_title:
        return proxy_late(platform, name, "default_title_only")

    return proxy_late(platform, name, "ambiguous")


class GunsChecker:
    platform = "guns"

    def check(self, target: str, proxy_url: str) -> CheckResult:
        name = target.strip().lstrip("@")
        url = f"https://guns.lol/{name}"
        headers = {
            **BROWSER_HEADERS,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Referer": "https://guns.lol/",
        }
        try:
            resp = get_session().get(
                url,
                headers=headers,
                proxies=proxy_dict(proxy_url),
                timeout=GUNS_TIMEOUT,
                allow_redirects=True,
            )
            body = resp.text
            if resp.status_code == 429:
                retry_after = (
                    resp.headers.get("Retry-After")
                    or resp.headers.get("retry-after")
                    or resp.headers.get("X-RateLimit-Reset-After")
                    or resp.headers.get("x-ratelimit-reset-after")
                )
                # Short default — a 2s sleep per 429 was collapsing CPS to ~1.5.
                detail = "retry_after=0.45"
                if retry_after:
                    try:
                        detail = f"retry_after={min(float(retry_after), 2.0)}"
                    except ValueError:
                        pass
                return CheckResult(name, self.platform, Status.RATE_LIMITED, detail)
            if is_rate_limited(resp.status_code, body):
                return CheckResult(name, self.platform, Status.RATE_LIMITED, "retry_after=0.45")
            if is_proxy_http(resp.status_code):
                return proxy_late(self.platform, name, f"http_{resp.status_code}")
            if resp.status_code not in (200, 404):
                return proxy_late(self.platform, name, f"http_{resp.status_code}")
            return classify_guns_html(name, body, status=resp.status_code)
        except requests.TooManyRedirects:
            return proxy_late(self.platform, name, "redirect_loop")
        except requests.Timeout:
            return proxy_late(self.platform, name, "timeout")
        except REQUEST_ERRORS as exc:
            msg = str(exc).lower()
            if "redirect" in msg or "too many" in msg:
                return proxy_late(self.platform, name, "redirect_loop")
            return proxy_late(self.platform, name, str(exc)[:80])
