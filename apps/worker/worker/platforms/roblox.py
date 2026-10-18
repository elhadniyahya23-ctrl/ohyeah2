from __future__ import annotations

import httpx

from worker.platforms._http import response_indicates_rate_limit
from worker.platforms.base import CheckOutcome, CheckResult, PlatformChecker


class RobloxChecker(PlatformChecker):
    platform = "roblox"

    async def check(self, client: httpx.AsyncClient, name: str) -> CheckResult:
        url = "https://auth.roblox.com/v1/usernames/validate"
        body = {"username": name, "birthday": "2000-01-01T07:00:00.000Z"}
        resp = await client.post(url, json=body)

        if response_indicates_rate_limit(resp.status_code, resp.text):
            return CheckResult(name, CheckOutcome.RATE_LIMITED)
        if resp.status_code == 429:
            return CheckResult(name, CheckOutcome.RATE_LIMITED)
        if resp.status_code != 200:
            return CheckResult(name, CheckOutcome.ERROR, f"http_{resp.status_code}")

        data = resp.json()
        code = data.get("code")

        # 0 = username is valid and available for registration
        if code == 0:
            return CheckResult(name, CheckOutcome.AVAILABLE)
        # 1/2/10 etc = taken, inappropriate, too short...
        if code in (1, 2, 3, 4, 10, 11, 12):
            return CheckResult(name, CheckOutcome.TAKEN)

        return CheckResult(name, CheckOutcome.ERROR, f"code_{code}")
