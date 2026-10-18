from __future__ import annotations

import httpx

from worker.platforms._http import BROWSER_HEADERS, response_indicates_rate_limit
from worker.platforms.base import CheckOutcome, CheckResult, PlatformChecker

IG_APP_ID = "936619743392459"


class InstagramChecker(PlatformChecker):
    platform = "instagram"

    async def check(self, client: httpx.AsyncClient, name: str) -> CheckResult:
        resp = await client.get(
            "https://i.instagram.com/api/v1/users/web_profile_info/",
            params={"username": name},
            headers={
                **BROWSER_HEADERS,
                "x-ig-app-id": IG_APP_ID,
                "Accept": "*/*",
            },
        )

        if response_indicates_rate_limit(resp.status_code, resp.text):
            return CheckResult(name, CheckOutcome.RATE_LIMITED)
        if resp.status_code == 429:
            return CheckResult(name, CheckOutcome.RATE_LIMITED)
        if resp.status_code == 404:
            return CheckResult(name, CheckOutcome.AVAILABLE)
        if resp.status_code != 200:
            return CheckResult(name, CheckOutcome.ERROR, f"http_{resp.status_code}")

        data = resp.json()
        user = data.get("data", {}).get("user")
        if user and user.get("username"):
            return CheckResult(name, CheckOutcome.TAKEN)

        return CheckResult(name, CheckOutcome.AVAILABLE)
