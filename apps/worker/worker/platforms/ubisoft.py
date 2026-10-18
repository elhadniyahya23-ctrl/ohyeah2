from __future__ import annotations

import secrets

import httpx

from worker.platforms._http import browser_headers, is_blocked_response
from worker.platforms.base import CheckOutcome, CheckResult, PlatformChecker

# PC / R6 live AppId — Connect web AppId is DataDome-gated.
CONNECT_APP_ID = "e3d5ea9e-50bd-43b7-88bf-39794f4e3d40"
VALIDATE_URL = "https://public-ubiservices.ubi.com/v3/users/validatecreation"


class UbisoftChecker(PlatformChecker):
    platform = "ubisoft"

    async def check(self, client: httpx.AsyncClient, name: str) -> CheckResult:
        email = f"us{secrets.token_hex(8)}@mailinator.com"
        payload = {
            "email": email,
            "confirmedEmail": email,
            "firstName": "User",
            "lastName": "Sniper",
            "nameOnPlatform": name,
            "legalOptinsKey": "",
            "isDateOfBirthApprox": False,
            "age": None,
            "dateOfBirth": "2000-12-12T00:00:00.000Z",
            "password": "Never_Want3d@to1Aa",
            "country": "US",
            "preferredLanguage": "en",
        }

        resp = await client.post(
            VALIDATE_URL,
            json=payload,
            headers={
                **browser_headers(),
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Ubi-AppId": CONNECT_APP_ID,
                "Ubi-RequestedPlatformType": "uplay",
            },
        )

        return _parse_validatecreation(name, resp)


def _parse_validatecreation(name: str, resp: httpx.Response) -> CheckResult:
    body = resp.text
    lower = body.lower()

    # Captcha = rotate exit; do not treat as pool-wide rate limit.
    if "captcha-delivery" in lower or "geo.captcha" in lower:
        return CheckResult(name, CheckOutcome.RATE_LIMITED)

    if is_blocked_response(resp) or resp.status_code == 429 or "too many calls" in lower:
        return CheckResult(name, CheckOutcome.RATE_LIMITED)

    if "nameonplatform" in lower and any(
        marker in lower
        for marker in (
            "already used",
            "already exists",
            "already taken",
            "is already",
            "not available",
            "invalid nameonplatform",
        )
    ):
        return CheckResult(name, CheckOutcome.TAKEN)

    if "legaloptinskey" in lower and "invalid nameonplatform" not in lower:
        return CheckResult(name, CheckOutcome.AVAILABLE)

    if resp.status_code == 200:
        return CheckResult(name, CheckOutcome.AVAILABLE)

    try:
        data = resp.json()
    except Exception:
        return CheckResult(name, CheckOutcome.ERROR, "ambiguous")

    if isinstance(data, dict):
        message = str(data.get("message", "")).lower()
        if "nameonplatform" in message and any(
            word in message for word in ("already", "used", "exists", "taken")
        ):
            return CheckResult(name, CheckOutcome.TAKEN)

        errors = data.get("errors") or data.get("errorFields") or {}
        if isinstance(errors, dict):
            name_errors = errors.get("nameOnPlatform") or errors.get("nameonplatform")
            if name_errors:
                return CheckResult(name, CheckOutcome.TAKEN)

        if "legaloptinskey" in lower:
            return CheckResult(name, CheckOutcome.AVAILABLE)

    return CheckResult(name, CheckOutcome.ERROR, "ambiguous")
