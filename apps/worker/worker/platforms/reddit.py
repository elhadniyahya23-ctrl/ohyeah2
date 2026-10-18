from __future__ import annotations

import httpx

from worker.platforms._http import response_indicates_rate_limit
from worker.platforms.base import CheckOutcome, CheckResult, PlatformChecker


class RedditChecker(PlatformChecker):
    platform = "reddit"

    async def check(self, client: httpx.AsyncClient, name: str) -> CheckResult:
        url = f"https://www.reddit.com/user/{name}/about.json"
        resp = await client.get(url, headers={"User-Agent": "UserSniper/1.0"})

        if response_indicates_rate_limit(resp.status_code, resp.text):
            return CheckResult(name, CheckOutcome.RATE_LIMITED)
        if resp.status_code == 429:
            return CheckResult(name, CheckOutcome.RATE_LIMITED)
        if resp.status_code == 404:
            return CheckResult(name, CheckOutcome.AVAILABLE)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("data", {}).get("name"):
                return CheckResult(name, CheckOutcome.TAKEN)
            return CheckResult(name, CheckOutcome.AVAILABLE)

        return CheckResult(name, CheckOutcome.ERROR, f"http_{resp.status_code}")
