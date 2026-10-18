from __future__ import annotations

import requests

from sniper.checkers.common import REQUEST_ERRORS, REQUEST_TIMEOUT, is_proxy_http, is_rate_limited, proxy_late
from sniper.http_util import get_session, proxy_dict
from sniper.turbo_engine import CheckResult, Status


class GitHubChecker:
    platform = "github"

    def check(self, target: str, proxy_url: str) -> CheckResult:
        name = target.strip()
        url = f"https://api.github.com/users/{name}"
        headers = {"Accept": "application/vnd.github+json", "User-Agent": "UserSniper-Turbo/1.0"}
        try:
            resp = get_session().get(
                url,
                headers=headers,
                proxies=proxy_dict(proxy_url),
                timeout=REQUEST_TIMEOUT,
            )
            body = resp.text
            if is_rate_limited(resp.status_code, body):
                return CheckResult(name, self.platform, Status.RATE_LIMITED, "rate_limit")
            if is_proxy_http(resp.status_code):
                return proxy_late(self.platform, name, f"http_{resp.status_code}")
            if resp.status_code == 404:
                return CheckResult(name, self.platform, Status.AVAILABLE)
            if resp.status_code == 200:
                return CheckResult(name, self.platform, Status.TAKEN)
            return CheckResult(name, self.platform, Status.ERROR, f"http_{resp.status_code}")
        except requests.Timeout:
            return proxy_late(self.platform, name, "timeout")
        except REQUEST_ERRORS as exc:
            return proxy_late(self.platform, name, str(exc)[:80])
