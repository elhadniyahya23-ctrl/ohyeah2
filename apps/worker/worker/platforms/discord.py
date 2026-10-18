from __future__ import annotations

import json

import httpx

from worker.platforms._http import browser_headers, parse_retry_after, response_indicates_rate_limit
from worker.platforms.base import CheckOutcome, CheckResult, PlatformChecker

DISCORD_ATTEMPT_URL = "https://discord.com/api/v9/unique-username/username-attempt-unauthed"

DISCORD_HEADERS = {
    **browser_headers(origin="https://discord.com", referer="https://discord.com/register"),
    "Accept": "application/json",
    "Content-Type": "application/json",
}


def _rate_limit_detail(status_code: int, text: str, headers: dict[str, str]) -> str:
    delay = parse_retry_after(status_code, text, headers)
    if delay is not None:
        return f"retry:{delay}"
    if status_code == 403:
        return "retry:5"
    return "retry:2.5"


def parse_attempt_response(name: str, status_code: int, text: str, headers: dict[str, str] | None = None) -> CheckResult:
    hdrs = headers or {}
    if response_indicates_rate_limit(status_code, text):
        return CheckResult(name, CheckOutcome.RATE_LIMITED, _rate_limit_detail(status_code, text, hdrs))

    if status_code == 400:
        try:
            data = json.loads(text)
        except Exception:
            return CheckResult(name, CheckOutcome.ERROR, "http_400")
        if isinstance(data, dict):
            message = str(data.get("message", "")).lower()
            code = data.get("code")
            if code in (50035, 50039, 50109) or "invalid" in message or "taken" in message:
                return CheckResult(name, CheckOutcome.TAKEN, f"code_{code}" if code else "http_400")
        return CheckResult(name, CheckOutcome.ERROR, "http_400")

    if status_code != 200:
        if status_code in (401, 403, 429, 503):
            return CheckResult(name, CheckOutcome.RATE_LIMITED, _rate_limit_detail(status_code, text, hdrs))
        return CheckResult(name, CheckOutcome.ERROR, f"http_{status_code}")

    try:
        data = json.loads(text)
    except Exception:
        if "<html" in text.lower():
            return CheckResult(name, CheckOutcome.RATE_LIMITED, "bad_json_html")
        return CheckResult(name, CheckOutcome.ERROR, "bad_json")

    if not isinstance(data, dict):
        return CheckResult(name, CheckOutcome.ERROR, "bad_response")

    code = data.get("code")
    message = str(data.get("message", "")).lower()
    if "rate limit" in message or data.get("retry_after") is not None:
        delay = parse_retry_after(200, text, hdrs)
        detail = f"retry:{delay}" if delay is not None else "retry:2.5"
        return CheckResult(name, CheckOutcome.RATE_LIMITED, detail)
    if code == 50039 or "invalid" in message:
        return CheckResult(name, CheckOutcome.TAKEN, "invalid_username")

    if "taken" in data:
        return CheckResult(
            name,
            CheckOutcome.TAKEN if data["taken"] else CheckOutcome.AVAILABLE,
        )
    if "available" in data:
        return CheckResult(
            name,
            CheckOutcome.AVAILABLE if data["available"] else CheckOutcome.TAKEN,
        )
    if code in (50035, 50109):
        return CheckResult(name, CheckOutcome.TAKEN, f"code_{code}")

    return CheckResult(name, CheckOutcome.ERROR, "ambiguous")


def _parse_attempt(name: str, resp: httpx.Response) -> CheckResult:
    return parse_attempt_response(name, resp.status_code, resp.text, dict(resp.headers))


class DiscordChecker(PlatformChecker):
    platform = "discord"

    async def check(self, client: httpx.AsyncClient, name: str) -> CheckResult:
        resp = await client.post(
            DISCORD_ATTEMPT_URL,
            json={"username": name},
            headers=DISCORD_HEADERS,
        )
        return _parse_attempt(name, resp)
