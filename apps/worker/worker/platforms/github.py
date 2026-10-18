from __future__ import annotations

import httpx

from worker.platforms._http import response_indicates_rate_limit
from worker.platforms.base import CheckOutcome, CheckResult, PlatformChecker


class GitHubChecker(PlatformChecker):
    platform = "github"

    async def check(self, client: httpx.AsyncClient, name: str) -> CheckResult:
        url = f"https://api.github.com/users/{name}"
        resp = await client.get(url, headers={"Accept": "application/vnd.github+json"})

        if response_indicates_rate_limit(resp.status_code, resp.text):
            return CheckResult(name, CheckOutcome.RATE_LIMITED)
        if resp.status_code == 429:
            return CheckResult(name, CheckOutcome.RATE_LIMITED)
        if resp.status_code == 404:
            return CheckResult(name, CheckOutcome.AVAILABLE)
        if resp.status_code == 200:
            return CheckResult(name, CheckOutcome.TAKEN)

        return CheckResult(name, CheckOutcome.ERROR, f"http_{resp.status_code}")
