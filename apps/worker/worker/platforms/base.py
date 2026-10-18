from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class CheckOutcome(str, Enum):
    AVAILABLE = "available"
    TAKEN = "taken"
    RATE_LIMITED = "rate_limited"
    ERROR = "error"


@dataclass
class CheckResult:
    name: str
    outcome: CheckOutcome
    detail: str = ""


class PlatformChecker:
    """Each platform implements a single availability check against its endpoint."""

    platform: str
    uses_endpoint: bool = True

    async def check(self, client, name: str) -> CheckResult:
        raise NotImplementedError
