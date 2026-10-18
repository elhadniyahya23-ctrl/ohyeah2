from __future__ import annotations

import httpx

from worker.platforms._http import browser_headers, is_blocked_response
from worker.platforms.base import CheckOutcome, CheckResult, PlatformChecker

VALIDATE_URL = "https://www.epicgames.com/id/api/account/displayName/validate"


class EpicChecker(PlatformChecker):
    platform = "epic"

    async def check(self, client: httpx.AsyncClient, name: str) -> CheckResult:
        resp = await client.post(
            VALIDATE_URL,
            json={"displayName": name},
            headers={
                **browser_headers(
                    origin="https://www.epicgames.com",
                    referer="https://www.epicgames.com/id/register?lang=en-US",
                ),
                "Content-Type": "application/json",
            },
        )

        if is_blocked_response(resp):
            return CheckResult(name, CheckOutcome.RATE_LIMITED)

        if resp.status_code == 429:
            return CheckResult(name, CheckOutcome.RATE_LIMITED)
        if resp.status_code != 200:
            return CheckResult(name, CheckOutcome.ERROR, f"http_{resp.status_code}")

        try:
            data = resp.json()
        except Exception:
            return CheckResult(name, CheckOutcome.ERROR, "bad_response")

        if data.get("available") is True:
            return CheckResult(name, CheckOutcome.AVAILABLE)
        if data.get("available") is False:
            return CheckResult(name, CheckOutcome.TAKEN)

        error = str(data.get("errorCode", "")).lower()
        if "taken" in error or "not_available" in error or "in_use" in error:
            return CheckResult(name, CheckOutcome.TAKEN)
        if "available" in error:
            return CheckResult(name, CheckOutcome.AVAILABLE)

        return CheckResult(name, CheckOutcome.ERROR, "ambiguous")
