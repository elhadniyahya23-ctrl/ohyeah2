from __future__ import annotations

import httpx

from worker.platforms._http import BROWSER_HEADERS, response_indicates_rate_limit
from worker.platforms.base import CheckOutcome, CheckResult, PlatformChecker


class TelegramChecker(PlatformChecker):
    platform = "telegram"

    async def check(self, client: httpx.AsyncClient, name: str) -> CheckResult:
        resp = await client.get(f"https://t.me/{name}", headers=BROWSER_HEADERS)

        if response_indicates_rate_limit(resp.status_code, resp.text):
            return CheckResult(name, CheckOutcome.RATE_LIMITED)
        if resp.status_code == 429:
            return CheckResult(name, CheckOutcome.RATE_LIMITED)
        if resp.status_code != 200:
            return CheckResult(name, CheckOutcome.ERROR, f"http_{resp.status_code}")

        body = resp.text.lower()
        if "tgme_page_photo" in body or "tgme_page_extra" in body:
            return CheckResult(name, CheckOutcome.TAKEN)
        if "you can contact" in body or "if you have <strong>telegram</strong>" in body:
            return CheckResult(name, CheckOutcome.AVAILABLE)

        return CheckResult(name, CheckOutcome.ERROR, "ambiguous")
