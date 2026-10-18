from __future__ import annotations

import json
import re

import requests

from sniper.checkers.common import (
    BROWSER_HEADERS,
    REQUEST_ERRORS,
    is_proxy_http,
    is_rate_limited,
    proxy_late,
)
from sniper.http_util import get_session, proxy_dict
from sniper.turbo_engine import CheckResult, Status

IG_APP_ID = "936619743392459"
IG_TIMEOUT = (5, 12)

_PAGE_UNAVAILABLE = (
    "sorry, this page isn't available",
    "page isn't available",
    "the link you followed may be broken",
)


def _from_api_payload(name: str, status: int, body: str) -> CheckResult | None:
    lower = body.lower()
    if status == 404:
        if "<html" in lower or "<!doctype" in lower:
            return None
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            return None
        if not isinstance(data, dict):
            return None
        msg = str(data.get("message", "")).lower()
        user = None
        data_obj = data.get("data")
        if isinstance(data_obj, dict):
            user = data_obj.get("user")
        if data.get("status") == "fail" or "user not found" in msg or user is None:
            return CheckResult(name, "instagram", Status.AVAILABLE, "api_404")
        return None

    if status != 200:
        return None
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    data_obj = data.get("data") if isinstance(data.get("data"), dict) else {}
    user = data_obj.get("user") if isinstance(data_obj, dict) else None
    if user and user.get("username"):
        return CheckResult(name, "instagram", Status.TAKEN, "api_user")
    if data.get("status") == "ok" and user is None:
        return CheckResult(name, "instagram", Status.AVAILABLE, "api_empty_user")
    return None


def _from_profile_html(name: str, status: int, body: str) -> CheckResult | None:
    lower = body.lower()
    if status == 404 or any(m in lower for m in _PAGE_UNAVAILABLE):
        return CheckResult(name, "instagram", Status.AVAILABLE, "page_unavailable")
    if status != 200:
        return None
    if re.search(rf'"username"\s*:\s*"{re.escape(name)}"', body, re.IGNORECASE):
        return CheckResult(name, "instagram", Status.TAKEN, "html_username")
    if '"ProfilePage"' in body or '"profilePage"' in body:
        return CheckResult(name, "instagram", Status.TAKEN, "html_profile")
    return None


class InstagramChecker:
    platform = "instagram"

    def check(self, target: str, proxy_url: str) -> CheckResult:
        name = target.strip().lstrip("@").lower()
        api_headers = {
            **BROWSER_HEADERS,
            "x-ig-app-id": IG_APP_ID,
            "Accept": "*/*",
            "Referer": "https://www.instagram.com/",
            "Origin": "https://www.instagram.com",
        }
        try:
            resp = get_session().get(
                "https://i.instagram.com/api/v1/users/web_profile_info/",
                params={"username": name},
                headers=api_headers,
                proxies=proxy_dict(proxy_url),
                timeout=IG_TIMEOUT,
            )
            body = resp.text
            if is_rate_limited(resp.status_code, body):
                return CheckResult(name, self.platform, Status.RATE_LIMITED, "rate_limit")
            if resp.status_code in (401, 403):
                pass
            elif is_proxy_http(resp.status_code):
                return proxy_late(self.platform, name, f"http_{resp.status_code}")
            else:
                parsed = _from_api_payload(name, resp.status_code, body)
                if parsed is not None:
                    return parsed
                if resp.status_code not in (200, 404, 401, 403):
                    return CheckResult(
                        name, self.platform, Status.ERROR, f"http_{resp.status_code}"
                    )

            page_headers = {
                **BROWSER_HEADERS,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Referer": "https://www.instagram.com/",
            }
            resp = get_session().get(
                f"https://www.instagram.com/{name}/",
                headers=page_headers,
                proxies=proxy_dict(proxy_url),
                timeout=IG_TIMEOUT,
                allow_redirects=True,
            )
            body = resp.text
            if is_rate_limited(resp.status_code, body):
                return CheckResult(name, self.platform, Status.RATE_LIMITED, "rate_limit")
            if is_proxy_http(resp.status_code) and resp.status_code != 404:
                return proxy_late(self.platform, name, f"http_{resp.status_code}")
            parsed = _from_profile_html(name, resp.status_code, body)
            if parsed is not None:
                return parsed
            if "login" in body.lower() and "instagram" in body.lower() and len(body) < 5000:
                return proxy_late(self.platform, name, "login_wall")
            return proxy_late(self.platform, name, "ambiguous")
        except requests.Timeout:
            return proxy_late(self.platform, name, "timeout")
        except REQUEST_ERRORS as exc:
            return proxy_late(self.platform, name, str(exc)[:80])
