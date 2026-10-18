from fastapi import Request


def client_ip(request: Request) -> str | None:
    """Best-effort real client IP behind Vercel → nginx → API."""
    # Prefer explicit real-IP from our Next.js proxy (set from Vercel edge).
    real = (request.headers.get("x-real-ip") or "").strip()
    if real:
        return real.split(",")[0].strip() or None

    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        # Left-most is the original client when proxies append.
        return forwarded.split(",")[0].strip() or None

    # Custom header our Vercel proxy may set
    client = (request.headers.get("x-client-ip") or "").strip()
    if client:
        return client.split(",")[0].strip() or None

    if request.client:
        return request.client.host
    return None
