"""TikTok username checker — profile URL tiktok.com/@user only."""

from __future__ import annotations

import json
import re
from urllib.parse import urlparse

import requests

from sniper.checkers.common import BROWSER_HEADERS, REQUEST_ERRORS, is_proxy_http, is_rate_limited, proxy_late
from sniper.http_util import get_session, proxy_dict
from sniper.turbo_engine import CheckResult, Status

# Empirically: real free handles return 10221 + empty statusMsg + no userInfo.
# 10202 (USER_NOT_EXIST enum) shows up on short/reserved ghosts that are NOT claimable.
AVAILABLE_STATUS_CODES = {10221}
TAKEN_STATUS_CODES = {0, 10222}
FALSE_AVAILABLE_CODES = {10202}
NON_USERNAME_CODES = {10209, 10211, 10225}
TIKTOK_TIMEOUT = (5, 12)

_TAKEN_STATUS_MSG_MARKERS = (
    "ban",
    "banned",
    "private",
    "secret",
    "restrict",
    "violat",
    "ftc",
    "under age",
    "underage",
)

_CHALLENGE_MARKERS = (
    "captcha",
    "_waf",
    "please wait",
    "access denied",
    "verify you are human",
)

_UNIVERSAL_RE = re.compile(
    r'<script[^>]+id="__UNIVERSAL_DATA_FOR_REHYDRATION__"[^>]*>(.*?)</script>',
    re.IGNORECASE | re.DOTALL,
)

# Official profile path: https://www.tiktok.com/@{user}
# Letters, numbers, . _ — 2–24 chars. Period cannot end the username.
_TIKTOK_USER_RE = re.compile(r"^[a-z0-9._]{2,24}$")
_PROFILE_PATH_RE = re.compile(r"^/@([A-Za-z0-9._]+)/?$")
_URL_USER_RE = re.compile(
    r"(?:https?://)?(?:www\.)?tiktok\.com/@([A-Za-z0-9._]+)",
    re.IGNORECASE,
)


def normalize_tiktok_username(raw: str) -> str:
    """Extract the @user slug from a bare name or tiktok.com/@user URL."""
    text = (raw or "").strip()
    if not text:
        return ""
    match = _URL_USER_RE.search(text)
    if match:
        return match.group(1).lower()
    return text.lstrip("@").strip().lower()


def tiktok_profile_url(name: str) -> str:
    """Canonical profile URL format used by TikTok web."""
    return f"https://www.tiktok.com/@{name}"


def tiktok_inappropriate_reason(name: str) -> str | None:
    """Return a detail if the handle cannot appear as tiktok.com/@user."""
    n = normalize_tiktok_username(name)
    if not n:
        return "inappropriate"
    if len(n) < 2 or len(n) > 24:
        return "inappropriate"
    if n.startswith(".") or n.endswith("."):
        return "inappropriate"
    if n.startswith("_") or n.endswith("_"):
        return "inappropriate"
    if ".." in n:
        return "inappropriate"
    if not _TIKTOK_USER_RE.fullmatch(n):
        return "inappropriate"
    core = n.replace(".", "").replace("_", "")
    if core.isdigit():
        return "inappropriate"
    if not any(ch.isalpha() for ch in n):
        return "inappropriate"
    return None


def _user_from_profile_url(url: str) -> str | None:
    path = urlparse(url).path or ""
    match = _PROFILE_PATH_RE.match(path)
    return match.group(1).lower() if match else None


def _user_detail_from_universal(body: str) -> dict | None:
    match = _UNIVERSAL_RE.search(body)
    if not match:
        return None
    try:
        data = json.loads(match.group(1))
    except (TypeError, json.JSONDecodeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    scope = data.get("__DEFAULT_SCOPE__")
    if not isinstance(scope, dict):
        return None
    detail = scope.get("webapp.user-detail")
    return detail if isinstance(detail, dict) else None


def _canonical_user_from_body(body: str) -> str | None:
    match = _UNIVERSAL_RE.search(body)
    if not match:
        return None
    try:
        data = json.loads(match.group(1))
    except (TypeError, json.JSONDecodeError, ValueError):
        return None
    scope = data.get("__DEFAULT_SCOPE__") if isinstance(data, dict) else None
    if not isinstance(scope, dict):
        return None
    seo = scope.get("seo.abtest")
    if not isinstance(seo, dict):
        return None
    canonical = seo.get("canonical")
    if not isinstance(canonical, str):
        return None
    return _user_from_profile_url(canonical)


def _unique_id_from_detail(detail: dict) -> str | None:
    user_info = detail.get("userInfo")
    if not isinstance(user_info, dict):
        return None
    user = user_info.get("user")
    if not isinstance(user, dict):
        return None
    uid = user.get("uniqueId")
    return str(uid) if uid else None


def _status_msg_blocks_available(msg: object) -> bool:
    text = str(msg or "").strip().lower()
    if not text:
        return False
    return any(marker in text for marker in _TAKEN_STATUS_MSG_MARKERS)


def _classify_status(
    name: str,
    code: int,
    *,
    status_msg: object = "",
    has_user: bool = False,
    unique_id: str | None = None,
    page_user: str | None = None,
) -> CheckResult:
    platform = "tiktok"
    needle = normalize_tiktok_username(name)
    uid = (unique_id or "").lower()
    page = (page_user or "").lower()

    # Response must still be the tiktok.com/@user profile for this handle.
    if page and page != needle:
        return CheckResult(name, platform, Status.TAKEN, f"redirect=@{page}")

    if uid and uid == needle:
        return CheckResult(name, platform, Status.TAKEN, "uniqueId")
    if has_user:
        return CheckResult(name, platform, Status.TAKEN, "userInfo")
    if code in TAKEN_STATUS_CODES:
        return CheckResult(name, platform, Status.TAKEN, f"status_{code}")
    if code in FALSE_AVAILABLE_CODES:
        return CheckResult(name, platform, Status.TAKEN, f"status_{code}_unclaimable")
    if code in NON_USERNAME_CODES:
        return CheckResult(name, platform, Status.ERROR, f"status_{code}")
    if code in AVAILABLE_STATUS_CODES:
        if _status_msg_blocks_available(status_msg):
            return CheckResult(name, platform, Status.TAKEN, f"status_{code}_banned")
        # Free page must still resolve as /@needle — never capture a mismatched shell page.
        if page and page != needle:
            return CheckResult(name, platform, Status.ERROR, "canonical_mismatch")
        return CheckResult(name, platform, Status.AVAILABLE, f"status_{code}")
    return CheckResult(name, platform, Status.ERROR, f"status_{code}")


def classify_tiktok_html(
    name: str,
    body: str,
    *,
    status: int,
    final_url: str | None = None,
) -> CheckResult:
    """Classify a TikTok profile HTML/JSON body for tiktok.com/@user."""
    platform = "tiktok"
    lower = body.lower()
    needle = normalize_tiktok_username(name)

    bad = tiktok_inappropriate_reason(needle)
    if bad:
        return CheckResult(needle, platform, Status.TAKEN, bad)

    if any(m in lower for m in _CHALLENGE_MARKERS) and "webapp.user-detail" not in lower and "statuscode" not in lower:
        return CheckResult(needle, platform, Status.RATE_LIMITED, "challenge")

    page_user = _user_from_profile_url(final_url or "") or _canonical_user_from_body(body)

    detail = _user_detail_from_universal(body)
    if detail is not None and "statusCode" in detail:
        try:
            code = int(detail["statusCode"])
        except (TypeError, ValueError):
            return CheckResult(needle, platform, Status.ERROR, "bad_status_code")
        has_user = isinstance(detail.get("userInfo"), dict) and isinstance(
            (detail.get("userInfo") or {}).get("user"), dict
        )
        return _classify_status(
            needle,
            code,
            status_msg=detail.get("statusMsg"),
            has_user=has_user,
            unique_id=_unique_id_from_detail(detail),
            page_user=page_user,
        )

    if re.search(rf'"uniqueId"\s*:\s*"{re.escape(needle)}"', body, re.IGNORECASE):
        return CheckResult(needle, platform, Status.TAKEN, "uniqueId")

    if "<html" not in lower and len(body) < 200:
        return proxy_late(platform, needle, "short_body")

    return CheckResult(needle, platform, Status.ERROR, "no_user_detail")


class TikTokChecker:
    platform = "tiktok"

    def check(self, target: str, proxy_url: str) -> CheckResult:
        name = normalize_tiktok_username(target)
        bad = tiktok_inappropriate_reason(name)
        if bad:
            return CheckResult(name, self.platform, Status.TAKEN, bad)
        headers = {
            **BROWSER_HEADERS,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Referer": "https://www.tiktok.com/",
        }
        url = tiktok_profile_url(name)
        try:
            resp = get_session().get(
                url,
                headers=headers,
                proxies=proxy_dict(proxy_url),
                timeout=TIKTOK_TIMEOUT,
                allow_redirects=True,
            )
            body = resp.text
            if is_rate_limited(resp.status_code, body):
                return CheckResult(name, self.platform, Status.RATE_LIMITED, "rate_limit")
            if resp.status_code == 429:
                return CheckResult(name, self.platform, Status.RATE_LIMITED, "http_429")
            if is_proxy_http(resp.status_code):
                return proxy_late(self.platform, name, f"http_{resp.status_code}")
            if resp.status_code not in (200, 404):
                return CheckResult(name, self.platform, Status.ERROR, f"http_{resp.status_code}")
            return classify_tiktok_html(
                name,
                body,
                status=resp.status_code,
                final_url=str(resp.url),
            )
        except requests.Timeout:
            return proxy_late(self.platform, name, "timeout")
        except REQUEST_ERRORS as exc:
            return proxy_late(self.platform, name, str(exc)[:80])
