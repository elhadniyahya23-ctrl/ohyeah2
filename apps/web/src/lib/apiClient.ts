import { getApiBase } from "@/lib/apiBase";
import { getStoredToken } from "@/lib/auth";

const DEFAULT_TIMEOUT_MS = 15_000;

export async function apiFetch(
  path: string,
  init?: RequestInit,
  timeoutMs = DEFAULT_TIMEOUT_MS,
): Promise<Response> {
  const token = getStoredToken();
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), timeoutMs);

  try {
    return await fetch(`${getApiBase()}${path}`, {
      ...init,
      signal: controller.signal,
      headers: {
        "Content-Type": "application/json",
        ...(token ? { "X-Session-Token": token } : {}),
        ...(init?.headers ?? {}),
      },
    });
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new Error("Server took too long to respond. Please try again.");
    }
    throw new Error("Cannot reach the API. Check your connection and try again.");
  } finally {
    window.clearTimeout(timer);
  }
}

export async function parseApiError(res: Response, fallback: string): Promise<never> {
  const data = await res.json().catch(() => ({}));
  const detail = (data as { detail?: unknown }).detail;
  if (typeof detail === "string") throw new Error(detail);
  if (Array.isArray(detail)) {
    const message = detail
      .map((item) => {
        if (typeof item === "object" && item && "msg" in item) {
          return String((item as { msg: string }).msg);
        }
        return String(item);
      })
      .join(", ");
    throw new Error(message || fallback);
  }
  throw new Error(fallback);
}
