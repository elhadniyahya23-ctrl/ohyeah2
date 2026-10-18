from __future__ import annotations

import asyncio
import logging

from sniper.discord_checker import DISCORD_HEADERS, DISCORD_TIMEOUT, SUGGESTIONS_URL
from sniper.http_util import get_session, proxy_dict
from sniper.proxy import ProxyRotator

logger = logging.getLogger(__name__)


def _probe_discord_proxy_sync(proxy_url: str) -> tuple[bool, str]:
    try:
        resp = get_session().get(
            SUGGESTIONS_URL,
            params={"global_name": "probe"},
            headers=DISCORD_HEADERS,
            proxies=proxy_dict(proxy_url),
            timeout=DISCORD_TIMEOUT,
        )
        body = resp.text
        if resp.status_code in (200, 400, 403, 429):
            return True, f"ok_{resp.status_code}"
        return False, f"http_{resp.status_code}:{body[:80]}"
    except Exception as exc:
        return False, str(exc)[:120]


async def probe_discord_proxy(proxy_url: str) -> tuple[bool, str]:
    """One lightweight Discord request to verify the proxy can reach the API."""
    return await asyncio.to_thread(_probe_discord_proxy_sync, proxy_url)


async def probe_proxy_lines(
    platform: str, proxy_lines: list[str], *, rotate_sessions: bool = False
) -> dict:
    if platform != "discord" or not proxy_lines:
        return {"ok": True, "skipped": True}
    rotator = ProxyRotator.from_lines(proxy_lines, rotate_sessions=rotate_sessions)
    url = rotator.next_url()
    ok, detail = await probe_discord_proxy(url)
    result = {"ok": ok, "detail": detail, "proxy_lines": len(proxy_lines)}
    if not ok:
        logger.warning("Discord proxy probe failed: %s (lines=%s)", detail, len(proxy_lines))
    return result
