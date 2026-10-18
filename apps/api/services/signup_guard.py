"""Client IP helpers for auth (registration / login metadata)."""

from __future__ import annotations

from ipaddress import ip_address


def normalize_ip(ip: str | None) -> str | None:
    if not ip:
        return None
    value = ip.strip()
    if not value:
        return None
    if value.startswith("::ffff:"):
        value = value[7:]
    try:
        return str(ip_address(value))
    except ValueError:
        return value


def client_ip_from_request(request) -> tuple[str | None, bool]:
    """Return (ip, from_trusted_edge_header)."""
    from services.request_utils import client_ip

    real = (request.headers.get("x-real-ip") or "").strip()
    if real:
        return normalize_ip(real.split(",")[0]), True

    client = (request.headers.get("x-client-ip") or "").strip()
    if client:
        return normalize_ip(client.split(",")[0]), True

    forwarded = (request.headers.get("x-forwarded-for") or "").strip()
    if forwarded:
        return normalize_ip(forwarded.split(",")[0]), True

    return normalize_ip(client_ip(request)), False
