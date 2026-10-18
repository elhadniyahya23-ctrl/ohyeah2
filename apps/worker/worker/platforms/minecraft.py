from __future__ import annotations

import httpx

from worker.platforms._http import response_indicates_rate_limit
from worker.platforms.base import CheckOutcome, CheckResult, PlatformChecker
from worker.platforms.minecraft_profanity import minecraft_inappropriate_reason


class MinecraftChecker(PlatformChecker):
    platform = "minecraft"

    async def check(self, client: httpx.AsyncClient, name: str) -> CheckResult:
        bad = minecraft_inappropriate_reason(name)
        if bad:
            return CheckResult(name, CheckOutcome.TAKEN, bad)

        url = f"https://api.mojang.com/users/profiles/minecraft/{name}"
        resp = await client.get(url)

        if response_indicates_rate_limit(resp.status_code, resp.text):
            return CheckResult(name, CheckOutcome.RATE_LIMITED)
        if resp.status_code == 429:
            return CheckResult(name, CheckOutcome.RATE_LIMITED)
        if resp.status_code == 404:
            return CheckResult(name, CheckOutcome.AVAILABLE)
        if resp.status_code == 200:
            return CheckResult(name, CheckOutcome.TAKEN)

        return CheckResult(name, CheckOutcome.ERROR, f"http_{resp.status_code}")
