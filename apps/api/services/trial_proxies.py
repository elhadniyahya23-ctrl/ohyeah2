"""Shared proxy pool used for Free Trial sniping (users don't bring their own)."""

from __future__ import annotations

from config import settings
from services.user_store import normalize_proxy_lines


def get_trial_proxies() -> list[str]:
    """Return configured trial proxies from TRIAL_PROXY_LINES (newline or comma separated)."""
    raw = (settings.trial_proxy_lines or "").strip()
    if not raw:
        return []
    # Support both newline-separated and comma-separated env values
    if "\n" in raw:
        lines = raw.splitlines()
    else:
        lines = [p.strip() for p in raw.split(",") if p.strip()]
    return normalize_proxy_lines(lines)


def user_can_manage_proxies(user) -> bool:
    """Paid / lifetime / admin users manage their own proxies. Trial users do not."""
    from services.plans import is_admin, is_trial_user

    if is_admin(user):
        return True
    if is_trial_user(user):
        return False
    # Premium / Lifetime / any non-trial with active plan
    from services.plans import user_has_active_plan

    return user_has_active_plan(user)
