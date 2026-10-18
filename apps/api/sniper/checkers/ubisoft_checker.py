"""Ubisoft Connect username checker via validatecreation (unauthenticated).

Connect web AppId is DataDome-gated. The PC / R6 live AppId reaches the real
API (taken / available / IP 429) without captcha, so we use that.
"""

from __future__ import annotations

import secrets

import requests

from sniper.checkers.common import (
    REQUEST_ERRORS,
    is_proxy_http,
    is_rate_limited,
    proxy_late,
    read_json_text,
)
from sniper.http_util import get_session, proxy_dict
from sniper.turbo_engine import CheckResult, Status

# Rainbow Six Siege PC LIVE — bypasses Connect DataDome interstitial.
CONNECT_APP_ID = "e3d5ea9e-50bd-43b7-88bf-39794f4e3d40"
VALIDATE_URL = "https://public-ubiservices.ubi.com/v3/users/validatecreation"
UBISOFT_TIMEOUT = (4, 12)

_TAKEN_MARKERS = (
    "already used",
    "already exists",
    "already taken",
    "is already",
    "not available",
    "invalid nameonplatform",
)


def classify_ubisoft_validate(name: str, body: str, *, status: int) -> CheckResult:
    """Parse Ubisoft validatecreation JSON/HTML.

    Captcha / DataDome must never look like a free hit — treat as proxy_late so
    the engine rotates exits instead of storm-pausing the whole job.
    A free name typically fails on legalOptinsKey; taken fails on nameOnPlatform.
    """
    platform = "ubisoft"
    lower = body.lower()

    # Captcha = bad exit, not a pool-wide rate limit.
    if "captcha-delivery" in lower or "geo.captcha" in lower:
        return proxy_late(platform, name, "captcha")

    if status == 429 or "too many calls" in lower:
        return CheckResult(name, platform, Status.RATE_LIMITED, "retry_after=1.5")

    if is_rate_limited(status, body):
        return CheckResult(name, platform, Status.RATE_LIMITED, "retry_after=1.5")

    if "nameonplatform" in lower and any(m in lower for m in _TAKEN_MARKERS):
        return CheckResult(name, platform, Status.TAKEN, "name_used")

    if "legaloptinskey" in lower and "invalid nameonplatform" not in lower:
        return CheckResult(name, platform, Status.AVAILABLE, "legal_optin")

    data = read_json_text(body)
    if isinstance(data, dict):
        message = str(data.get("message") or "").lower()
        if "nameonplatform" in message and any(
            w in message for w in ("already", "used", "exists", "taken", "invalid")
        ):
            return CheckResult(name, platform, Status.TAKEN, "message")

        errors = data.get("errors") or data.get("errorFields") or {}
        if isinstance(errors, dict):
            name_errors = errors.get("nameOnPlatform") or errors.get("nameonplatform")
            if name_errors:
                return CheckResult(name, platform, Status.TAKEN, "error_field")

        if "legaloptinskey" in lower:
            return CheckResult(name, platform, Status.AVAILABLE, "legal_optin")

    if status == 200 and "captcha" not in lower:
        return CheckResult(name, platform, Status.AVAILABLE, "http_200")

    if is_proxy_http(status):
        return proxy_late(platform, name, f"http_{status}")

    return CheckResult(name, platform, Status.ERROR, f"http_{status}")


class UbisoftChecker:
    platform = "ubisoft"

    def check(self, target: str, proxy_url: str) -> CheckResult:
        name = target.strip()
        if not name or len(name) < 3 or len(name) > 15:
            return CheckResult(name or target, self.platform, Status.ERROR, "bad_length")

        email = f"us{secrets.token_hex(8)}@mailinator.com"
        payload = {
            "email": email,
            "confirmedEmail": email,
            "firstName": "User",
            "lastName": "Sniper",
            "nameOnPlatform": name,
            "legalOptinsKey": "",
            "isDateOfBirthApprox": False,
            "age": None,
            "dateOfBirth": "2000-12-12T00:00:00.000Z",
            "password": "Never_Want3d@to1Aa",
            "country": "US",
            "preferredLanguage": "en",
        }
        # No Connect Origin/Referer — those headers trip DataDome on web AppIds.
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Ubi-AppId": CONNECT_APP_ID,
            "Ubi-RequestedPlatformType": "uplay",
        }
        try:
            resp = get_session().post(
                VALIDATE_URL,
                json=payload,
                headers=headers,
                proxies=proxy_dict(proxy_url),
                timeout=UBISOFT_TIMEOUT,
            )
            return classify_ubisoft_validate(name, resp.text, status=resp.status_code)
        except requests.Timeout:
            return proxy_late(self.platform, name, "timeout")
        except REQUEST_ERRORS as exc:
            return proxy_late(self.platform, name, str(exc)[:80])
