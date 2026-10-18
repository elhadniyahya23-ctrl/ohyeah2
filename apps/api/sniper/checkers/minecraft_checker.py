from __future__ import annotations

import json

import requests

from sniper.checkers.common import REQUEST_ERRORS, REQUEST_TIMEOUT, is_proxy_http, is_rate_limited, proxy_late
from sniper.checkers.minecraft_profanity import minecraft_inappropriate_reason
from sniper.http_util import get_session, proxy_dict
from sniper.turbo_engine import CheckResult, Status

__all__ = [
    "MinecraftChecker",
    "_mojang_available_body",
    "_mojang_taken_body",
    "minecraft_inappropriate_reason",
]

_MOJANG_NOT_FOUND_MARKERS = (
    "couldn't find any profile",
    "could not find",
    "no such profile",
    "not found",
)


def _mojang_available_body(status: int, body: str) -> bool:
    text = (body or "").strip()
    lower = text.lower()
    if status == 204:
        return True
    if status != 404:
        return False
    if not text:
        return False
    if "<html" in lower or "<!doctype" in lower:
        return False
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return any(m in lower for m in _MOJANG_NOT_FOUND_MARKERS)
    if isinstance(data, dict):
        if data.get("id") or data.get("name"):
            return False
        err = str(data.get("errorMessage") or data.get("error") or data.get("path") or "").lower()
        if any(m in err for m in _MOJANG_NOT_FOUND_MARKERS) or "profile" in err:
            return True
        if "errorMessage" in data or "error" in data:
            return True
    return any(m in lower for m in _MOJANG_NOT_FOUND_MARKERS)


def _mojang_taken_body(status: int, body: str) -> bool:
    if status != 200:
        return False
    try:
        data = json.loads(body or "")
    except json.JSONDecodeError:
        return False
    return isinstance(data, dict) and bool(data.get("id") or data.get("name"))


class MinecraftChecker:
    platform = "minecraft"

    def check(self, target: str, proxy_url: str) -> CheckResult:
        name = target.strip()
        bad = minecraft_inappropriate_reason(name)
        if bad:
            return CheckResult(name, self.platform, Status.TAKEN, bad)
        url = f"https://api.mojang.com/users/profiles/minecraft/{name}"
        try:
            resp = get_session().get(
                url,
                proxies=proxy_dict(proxy_url),
                timeout=REQUEST_TIMEOUT,
                headers={"Accept": "application/json"},
            )
            body = resp.text
            if is_rate_limited(resp.status_code, body):
                return CheckResult(name, self.platform, Status.RATE_LIMITED, "rate_limit")
            if is_proxy_http(resp.status_code):
                return proxy_late(self.platform, name, f"http_{resp.status_code}")
            if _mojang_taken_body(resp.status_code, body):
                return CheckResult(name, self.platform, Status.TAKEN)
            if _mojang_available_body(resp.status_code, body):
                return CheckResult(name, self.platform, Status.AVAILABLE)
            if resp.status_code in (404, 204):
                return proxy_late(self.platform, name, f"ambiguous_{resp.status_code}")
            return CheckResult(name, self.platform, Status.ERROR, f"http_{resp.status_code}")
        except requests.Timeout:
            return proxy_late(self.platform, name, "timeout")
        except REQUEST_ERRORS as exc:
            return proxy_late(self.platform, name, str(exc)[:80])
