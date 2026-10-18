from __future__ import annotations

import re

import httpx

from worker.platforms._http import BROWSER_HEADERS, response_indicates_rate_limit
from worker.platforms.base import CheckOutcome, CheckResult, PlatformChecker

DEFAULT_TITLE = "guns.lol: Everything you want, right here."
DEFAULT_TITLE_TR = "guns.lol: İstediğin her şey, burada."
NOT_FOUND_FRAGMENTS = ("username not found", "bulunamad")


class GunsChecker(PlatformChecker):
    platform = "guns"

    async def check(self, client: httpx.AsyncClient, name: str) -> CheckResult:
        resp = await client.get(f"https://guns.lol/{name}", headers=BROWSER_HEADERS)

        if response_indicates_rate_limit(resp.status_code, resp.text):
            return CheckResult(name, CheckOutcome.RATE_LIMITED)
        if resp.status_code == 429:
            return CheckResult(name, CheckOutcome.RATE_LIMITED)
        if resp.status_code not in (200, 404):
            return CheckResult(name, CheckOutcome.ERROR, f"http_{resp.status_code}")

        lower = resp.text.lower()
        if "cf-challenge" in lower or "just a moment" in lower:
            return CheckResult(name, CheckOutcome.RATE_LIMITED, "challenge")

        title_match = re.search(r"<title>([^<]+)</title>", resp.text, re.IGNORECASE)
        if not title_match:
            return CheckResult(name, CheckOutcome.ERROR, "no_title")

        title_l = title_match.group(1).strip().lower()
        needle = name.strip().lstrip("@").lower()
        if re.match(rf"^@{re.escape(needle)}\s*\|\s*guns\.lol$", title_l):
            return CheckResult(name, CheckOutcome.TAKEN)
        if re.search(r"^@\S+\s*\|\s*guns\.lol$", title_l):
            return CheckResult(name, CheckOutcome.TAKEN)

        is_default = title_l in {DEFAULT_TITLE.lower(), DEFAULT_TITLE_TR.lower()}
        has_not_found = any(f in lower for f in NOT_FOUND_FRAGMENTS)
        if is_default and has_not_found:
            return CheckResult(name, CheckOutcome.AVAILABLE)
        if is_default:
            return CheckResult(name, CheckOutcome.ERROR, "default_title_only")
        return CheckResult(name, CheckOutcome.ERROR, "ambiguous")
