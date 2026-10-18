from __future__ import annotations

import httpx

from worker.platforms._http import response_indicates_rate_limit
from worker.platforms.base import CheckOutcome, CheckResult, PlatformChecker


class SteamChecker(PlatformChecker):
    platform = "steam"

    async def check(self, client: httpx.AsyncClient, name: str) -> CheckResult:
        url = f"https://steamcommunity.com/id/{name}?xml=1"
        resp = await client.get(url)

        if response_indicates_rate_limit(resp.status_code, resp.text):
            return CheckResult(name, CheckOutcome.RATE_LIMITED)
        if resp.status_code == 429:
            return CheckResult(name, CheckOutcome.RATE_LIMITED)
        if resp.status_code != 200:
            return CheckResult(name, CheckOutcome.ERROR, f"http_{resp.status_code}")

        body = resp.text.lower()
        if "the specified profile could not be found" in body:
            return CheckResult(name, CheckOutcome.AVAILABLE)
        if "<steamid64>" in body:
            return CheckResult(name, CheckOutcome.TAKEN)

        return CheckResult(name, CheckOutcome.ERROR, "ambiguous")
