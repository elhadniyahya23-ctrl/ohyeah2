import type { PlatformId } from "@/lib/platforms";
import { apiFetch, parseApiError } from "@/lib/apiClient";
import type { SniperStatus } from "@/lib/sniperUi";

const START_TIMEOUT_MS = 60_000;

export async function fetchSniperStatus(platform: PlatformId): Promise<SniperStatus> {
  const res = await apiFetch(`/api/sniper/status?platform=${platform}`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to fetch sniper status");
  return res.json();
}

export async function fetchAllSniperStatuses(): Promise<Record<string, SniperStatus>> {
  const { TURBO_PLATFORMS } = await import("@/lib/platforms");
  const entries = await Promise.all(
    TURBO_PLATFORMS.map(async (id) => {
      try {
        const status = await fetchSniperStatus(id);
        return [id, status] as const;
      } catch {
        return [id, null] as const;
      }
    }),
  );
  const out: Record<string, SniperStatus> = {};
  for (const [id, status] of entries) {
    if (status) out[id] = status;
  }
  return out;
}

export async function startSniper(
  platform: PlatformId,
  names: string[] = [],
  proxies: string[] = [],
  infinite = false,
): Promise<{ total_names: number; resumed: boolean; infinite?: boolean }> {
  const res = await apiFetch(
    "/api/sniper/start",
    {
      method: "POST",
      body: JSON.stringify({ platform, names, proxies, mode: "sequential", infinite }),
    },
    START_TIMEOUT_MS,
  );
  if (res.status === 401) throw new Error("Please log in to run the sniper");
  if (res.status === 403) {
    const data = await res.json().catch(() => ({}));
    throw new Error(
      (data as { detail?: string }).detail ?? "Your plan has expired. Upgrade to continue.",
    );
  }
  if (res.status === 409) {
    const data = await res.json().catch(() => ({}));
    throw new Error(
      (data as { detail?: string }).detail ?? "Sniper already active for this platform",
    );
  }
  if (res.status === 429) {
    const data = await res.json().catch(() => ({}));
    throw new Error(
      (data as { detail?: string }).detail ??
        "Too many snipers running right now — wait a moment and try again.",
    );
  }
  if (res.status === 503) {
    const data = await res.json().catch(() => ({}));
    throw new Error(
      (data as { detail?: string }).detail ??
        "Sniper service is temporarily unavailable. Try again shortly.",
    );
  }
  if (res.status === 400) {
    await parseApiError(res, "Failed to start sniper");
  }
  if (res.status === 501) {
    await parseApiError(res, "This platform is not available yet");
  }
  if (!res.ok) {
    await parseApiError(res, "Failed to start sniper");
  }
  const data = (await res.json()) as { total_names?: number; resumed?: boolean; infinite?: boolean };
  return {
    total_names: data.total_names ?? 0,
    resumed: Boolean(data.resumed),
    infinite: Boolean(data.infinite),
  };
}

export async function stopSniper(platform: PlatformId): Promise<void> {
  const res = await apiFetch(`/api/sniper/stop?platform=${platform}`, { method: "POST" });
  if (!res.ok) throw new Error("Failed to stop sniper");
}

export async function clearSniperCaptures(): Promise<void> {
  const res = await apiFetch("/api/sniper/captures", { method: "DELETE" });
  if (!res.ok) throw new Error("Failed to clear results");
}

export interface SavedResult {
  name: string;
  platform: string;
  at: string | null;
  job_id?: string;
}

export async function fetchSavedResults(limit = 300): Promise<SavedResult[]> {
  const res = await apiFetch(`/api/sniper/results?limit=${limit}`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to load saved results");
  const data = await res.json();
  return data.results ?? [];
}
