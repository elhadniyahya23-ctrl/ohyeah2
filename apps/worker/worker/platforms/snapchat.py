from __future__ import annotations

import httpx

from worker.platforms._http import BROWSER_HEADERS, response_indicates_rate_limit
from worker.platforms.base import CheckOutcome, CheckResult, PlatformChecker


class SnapchatChecker(PlatformChecker):
    platform = "snapchat"

    async def check(self, client: httpx.AsyncClient, name: str) -> CheckResult:
        resp = await client.get(
            f"https://www.snapchat.com/add/{name}",
            headers=BROWSER_HEADERS,
        )

        if response_indicates_rate_limit(resp.status_code, resp.text):
            return CheckResult(name, CheckOutcome.RATE_LIMITED)
        if resp.status_code == 429:
            return CheckResult(name, CheckOutcome.RATE_LIMITED)
        if resp.status_code not in (200, 404):
            return CheckResult(name, CheckOutcome.ERROR, f"http_{resp.status_code}")

        body = resp.text
        if "add_user" in body or "snapchatCanonicalUrl" in body:
            return CheckResult(name, CheckOutcome.TAKEN)
        if "not_found" in body:
            return CheckResult(name, CheckOutcome.AVAILABLE)

        return CheckResult(name, CheckOutcome.ERROR, "ambiguous")
