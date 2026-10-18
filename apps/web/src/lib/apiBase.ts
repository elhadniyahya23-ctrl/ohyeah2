/** Browser calls same-origin /api (Vercel rewrite → VPS). Server/dev can override via env. */
export function getApiBase(): string {
  if (typeof window !== "undefined") {
    const configured = process.env.NEXT_PUBLIC_API_URL?.trim();
    if (configured && window.location.hostname === "localhost") {
      return configured.replace(/\/$/, "");
    }
    return "";
  }

  return (
    process.env.NEXT_PUBLIC_API_URL?.trim()?.replace(/\/$/, "") ??
    process.env.API_PROXY_URL?.replace(/\/$/, "") ??
    "http://localhost:8000"
  );
}
