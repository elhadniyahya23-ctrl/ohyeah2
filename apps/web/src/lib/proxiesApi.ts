import { apiFetch, parseApiError } from "@/lib/apiClient";

export async function fetchProxies(): Promise<{ proxies: string[]; count: number }> {
  const res = await apiFetch(`/api/proxies?_=${Date.now()}`, { cache: "no-store" });
  if (res.status === 401) throw new Error("Please log in to manage proxies");
  if (!res.ok) await parseApiError(res, "Failed to load proxies");
  return res.json();
}

export async function saveProxies(proxies: string[]): Promise<{
  count: number;
  ok?: boolean;
  proxies?: string[];
  duplicates?: number;
  invalid?: number;
}> {
  const res = await apiFetch("/api/proxies", {
    method: "POST",
    body: JSON.stringify({ proxies }),
  });
  if (res.status === 401) throw new Error("Please log in to manage proxies");
  if (res.status === 403) {
    throw new Error("Proxies unlock after you upgrade — Free Trial uses shared proxies.");
  }
  if (res.status === 502 || res.status === 503 || res.status === 504) {
    throw new Error("API is temporarily unreachable — try saving again in a moment.");
  }
  if (!res.ok) await parseApiError(res, "Failed to save proxies");
  return res.json();
}
