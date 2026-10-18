import { NextRequest, NextResponse } from "next/server";

/**
 * Vercel → Hostinger API proxy.
 *
 * Production notes:
 * - api.usersniper.com TLS on :443 is broken, so we always use plain HTTP.
 * - Prefer the VPS IP so DNS / CDN oddities cannot break POSTs.
 * - Only forward a small allowlist of headers — forwarding hop-by-hop /
 *   encoding headers from the browser breaks Node fetch POSTs on Vercel.
 */
function backendBase(): string {
  if (process.env.NODE_ENV === "development") {
    return (
      process.env.API_PROXY_URL?.trim().replace(/\/$/, "") ?? "http://localhost:8000"
    );
  }

  const raw = process.env.API_PROXY_URL?.trim().replace(/\/$/, "") ?? "";
  if (raw) {
    // Never use HTTPS for our API host — TLS handshake resets on :443.
    return raw
      .replace(/^https:\/\/api\.usersniper\.com/i, "http://api.usersniper.com")
      .replace(/^https:\/\/31\.97\.179\.26/i, "http://31.97.179.26");
  }

  // Default: hit the Hostinger control VPS by IP (HTTP only).
  return "http://31.97.179.26";
}

function backendHostHeader(base: string): string {
  try {
    const host = new URL(base).hostname;
    if (host === "31.97.179.26" || host === "localhost" || host === "127.0.0.1") {
      return "api.usersniper.com";
    }
    return host;
  } catch {
    return "api.usersniper.com";
  }
}

const FORWARD_HEADERS = new Set([
  "accept",
  "content-type",
  "x-session-token",
  "authorization",
  "cookie",
  "x-request-id",
]);

function clientIpFromRequest(req: NextRequest): string | null {
  const real = req.headers.get("x-real-ip")?.trim();
  if (real) return real.split(",")[0].trim() || null;
  const forwarded = req.headers.get("x-forwarded-for")?.trim();
  if (forwarded) return forwarded.split(",")[0].trim() || null;
  return null;
}

export const runtime = "nodejs";
export const maxDuration = 60;

async function proxy(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  const { path } = await ctx.params;
  const suffix = path.join("/");
  const url = new URL(req.url);
  const base = backendBase();
  const target = `${base}/api/${suffix}${url.search}`;

  const headers = new Headers();
  req.headers.forEach((value, key) => {
    if (FORWARD_HEADERS.has(key.toLowerCase())) {
      headers.set(key, value);
    }
  });
  headers.set("host", backendHostHeader(base));
  headers.set("x-forwarded-proto", "https");
  headers.set("x-forwarded-host", url.host);
  // Pass the real visitor IP through to the API (signup IP / VPN checks).
  const clientIp = clientIpFromRequest(req);
  if (clientIp) {
    headers.set("x-real-ip", clientIp);
    headers.set("x-client-ip", clientIp);
    headers.set("x-forwarded-for", clientIp);
  }
  // Avoid identity surprises from browser accept-encoding on the upstream hop.
  headers.set("accept-encoding", "identity");

  const init: RequestInit = {
    method: req.method,
    headers,
    redirect: "manual",
    cache: "no-store",
  };

  if (req.method !== "GET" && req.method !== "HEAD") {
    const body = await req.arrayBuffer();
    init.body = body;
    // Explicit length so upstream never sees a mismatched chunked body.
    headers.set("content-length", String(body.byteLength));
  }

  try {
    const res = await fetch(target, init);
    const outHeaders = new Headers();
    res.headers.forEach((value, key) => {
      const lower = key.toLowerCase();
      if (
        lower === "transfer-encoding" ||
        lower === "connection" ||
        lower === "keep-alive" ||
        lower === "content-encoding"
      ) {
        return;
      }
      outHeaders.set(key, value);
    });
    const buf = await res.arrayBuffer();
    return new NextResponse(buf, { status: res.status, headers: outHeaders });
  } catch (err) {
    const message = err instanceof Error ? err.message : "unknown error";
    console.error("[api-proxy]", req.method, target, message);
    return NextResponse.json(
      {
        detail: "Cannot reach the API backend",
        error: message,
        target: `${base}/api/${suffix}`,
      },
      { status: 502 },
    );
  }
}

export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
export const PATCH = proxy;
export const DELETE = proxy;
export const OPTIONS = proxy;
