from __future__ import annotations

import httpx

from worker.platforms._http import BROWSER_HEADERS, response_indicates_rate_limit
from worker.platforms.base import CheckOutcome, CheckResult, PlatformChecker


class TwitterChecker(PlatformChecker):
    platform = "twitter"

    async def check(self, client: httpx.AsyncClient, name: str) -> CheckResult:
        resp = await client.get(f"https://x.com/{name}", headers=BROWSER_HEADERS)

        if response_indicates_rate_limit(resp.status_code, resp.text):
            return CheckResult(name, CheckOutcome.RATE_LIMITED)
        if resp.status_code == 429:
            return CheckResult(name, CheckOutcome.RATE_LIMITED)
        if resp.status_code == 404:
            return CheckResult(name, CheckOutcome.AVAILABLE)
        if resp.status_code == 200:
            return CheckResult(name, CheckOutcome.TAKEN)

        return CheckResult(name, CheckOutcome.ERROR, f"http_{resp.status_code}")
