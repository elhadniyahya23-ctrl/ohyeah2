from __future__ import annotations

import json
import re
from urllib.parse import urlparse

import httpx

from worker.platforms._http import BROWSER_HEADERS, response_indicates_rate_limit
from worker.platforms.base import CheckOutcome, CheckResult, PlatformChecker

AVAILABLE_STATUS_CODES = {10221}
TAKEN_STATUS_CODES = {0, 10222}
FALSE_AVAILABLE_CODES = {10202}
NON_USERNAME_CODES = {10209, 10211, 10225}

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

_UNIVERSAL_RE = re.compile(
    r'<script[^>]+id="__UNIVERSAL_DATA_FOR_REHYDRATION__"[^>]*>(.*?)</script>',
    re.IGNORECASE | re.DOTALL,
)
_TIKTOK_USER_RE = re.compile(r"^[a-z0-9._]{2,24}$")
_PROFILE_PATH_RE = re.compile(r"^/@([A-Za-z0-9._]+)/?$")
_URL_USER_RE = re.compile(
    r"(?:https?://)?(?:www\.)?tiktok\.com/@([A-Za-z0-9._]+)",
    re.IGNORECASE,
)


def normalize_tiktok_username(raw: str) -> str:
    text = (raw or "").strip()
    if not text:
        return ""
    match = _URL_USER_RE.search(text)
    if match:
        return match.group(1).lower()
    return text.lstrip("@").strip().lower()


def tiktok_profile_url(name: str) -> str:
    return f"https://www.tiktok.com/@{name}"


def tiktok_inappropriate_reason(name: str) -> str | None:
    n = normalize_tiktok_username(name)
    if not n or len(n) < 2 or len(n) > 24:
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


def _status_msg_blocks_available(msg: object) -> bool:
    text = str(msg or "").strip().lower()
    if not text:
        return False
    return any(marker in text for marker in _TAKEN_STATUS_MSG_MARKERS)


def _classify(
    name: str,
    code: int,
    *,
    status_msg: object = "",
    user: object = None,
    page_user: str | None = None,
) -> CheckResult:
    needle = normalize_tiktok_username(name)
    uid = ""
    if isinstance(user, dict) and user.get("uniqueId"):
        uid = str(user["uniqueId"]).lower()
    page = (page_user or "").lower()
    if page and page != needle:
        return CheckResult(needle, CheckOutcome.TAKEN, f"redirect=@{page}")
    if uid and uid == needle:
        return CheckResult(needle, CheckOutcome.TAKEN)
    if isinstance(user, dict):
        return CheckResult(needle, CheckOutcome.TAKEN)
    if code in TAKEN_STATUS_CODES:
        return CheckResult(needle, CheckOutcome.TAKEN)
    if code in FALSE_AVAILABLE_CODES:
        return CheckResult(needle, CheckOutcome.TAKEN, "unclaimable")
    if code in NON_USERNAME_CODES:
        return CheckResult(needle, CheckOutcome.ERROR, f"status_{code}")
    if code in AVAILABLE_STATUS_CODES:
        if _status_msg_blocks_available(status_msg):
            return CheckResult(needle, CheckOutcome.TAKEN, "banned")
        return CheckResult(needle, CheckOutcome.AVAILABLE)
    return CheckResult(needle, CheckOutcome.ERROR, f"status_{code}")


class TikTokChecker(PlatformChecker):
    platform = "tiktok"

    async def check(self, client: httpx.AsyncClient, name: str) -> CheckResult:
        needle = normalize_tiktok_username(name)
        bad = tiktok_inappropriate_reason(needle)
        if bad:
            return CheckResult(needle, CheckOutcome.TAKEN, bad)

        resp = await client.get(tiktok_profile_url(needle), headers=BROWSER_HEADERS)

        if response_indicates_rate_limit(resp.status_code, resp.text):
            return CheckResult(needle, CheckOutcome.RATE_LIMITED)
        if resp.status_code == 429:
            return CheckResult(needle, CheckOutcome.RATE_LIMITED)
        if resp.status_code not in (200, 404):
            return CheckResult(needle, CheckOutcome.ERROR, f"http_{resp.status_code}")

        body = resp.text
        page_user = _user_from_profile_url(str(resp.url))
        match = _UNIVERSAL_RE.search(body)
        if match:
            try:
                data = json.loads(match.group(1))
                detail = (data.get("__DEFAULT_SCOPE__") or {}).get("webapp.user-detail")
                if page_user is None:
                    seo = (data.get("__DEFAULT_SCOPE__") or {}).get("seo.abtest") or {}
                    if isinstance(seo, dict) and isinstance(seo.get("canonical"), str):
                        page_user = _user_from_profile_url(seo["canonical"])
            except (TypeError, json.JSONDecodeError, ValueError, AttributeError):
                detail = None
            if isinstance(detail, dict) and "statusCode" in detail:
                try:
                    code = int(detail["statusCode"])
                except (TypeError, ValueError):
                    return CheckResult(needle, CheckOutcome.ERROR, "bad_status_code")
                user = ((detail.get("userInfo") or {}) if isinstance(detail.get("userInfo"), dict) else {}).get("user")
                return _classify(
                    needle,
                    code,
                    status_msg=detail.get("statusMsg"),
                    user=user,
                    page_user=page_user,
                )

        if re.search(rf'"uniqueId"\s*:\s*"{re.escape(needle)}"', body, re.IGNORECASE):
            return CheckResult(needle, CheckOutcome.TAKEN)
        return CheckResult(needle, CheckOutcome.ERROR, "no_user_detail")
