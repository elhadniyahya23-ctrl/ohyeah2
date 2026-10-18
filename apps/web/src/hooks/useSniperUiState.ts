"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  clearSniperCaptures,
  fetchAllSniperStatuses,
  fetchSniperStatus,
  startSniper,
  stopSniper,
} from "@/lib/sniperApi";
import { COMING_SOON_PLATFORMS, PLATFORMS, TURBO_PLATFORM_SET, type PlatformId } from "@/lib/platforms";
import { emptySniperStatus, type SniperStatus } from "@/lib/sniperUi";

/** Live dashboard: 1s is enough for CPS/progress; 300ms flooded Vercel→VPS. */
const POLL_ACTIVE_MS = 1000;
const POLL_IDLE_MS = 5000;

function initialStatuses(): Record<string, SniperStatus> {
  return Object.fromEntries(PLATFORMS.map((p) => [p.id, emptySniperStatus(p.id)]));
}

function isActive(state: string): boolean {
  return state === "running" || state === "queued";
}

export function useSniperUiState(platform: PlatformId) {
  const [statuses, setStatuses] = useState<Record<string, SniperStatus>>(initialStatuses);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const inFlightRef = useRef(false);

  const status = useMemo(
    () => statuses[platform] ?? emptySniperStatus(platform),
    [statuses, platform],
  );

  const refresh = useCallback(async () => {
    if (inFlightRef.current) return;
    if (typeof document !== "undefined" && document.visibilityState === "hidden") return;
    inFlightRef.current = true;
    try {
      const s = await fetchSniperStatus(platform);
      setStatuses((prev) => ({ ...prev, [platform]: s }));
    } catch {
      /* keep last known status — a transient API blip must not wipe captures */
    } finally {
      inFlightRef.current = false;
    }
  }, [platform]);

  const refreshAll = useCallback(async () => {
    try {
      const all = await fetchAllSniperStatuses();
      setStatuses((prev) => ({ ...prev, ...all }));
    } catch {
      /* keep last known */
    }
  }, []);

  useEffect(() => {
    void refresh();
    void refreshAll();
  }, [refresh, refreshAll]);

  useEffect(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
    const ms = isActive(status.state) ? POLL_ACTIVE_MS : POLL_IDLE_MS;
    pollRef.current = setInterval(() => {
      void refresh();
    }, ms);
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [refresh, status.state]);

  useEffect(() => {
    const onVisible = () => {
      if (document.visibilityState === "visible") void refresh();
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => document.removeEventListener("visibilitychange", onVisible);
  }, [refresh]);

  const clearCaptures = useCallback(async () => {
    await clearSniperCaptures();
    setStatuses((prev) => {
      const next = { ...prev };
      for (const key of Object.keys(next)) {
        next[key] = { ...next[key], captures: [] };
      }
      return next;
    });
  }, []);

  const requestStart = useCallback(
    async (names: string[] = [], proxies: string[] = [], infinite = false) => {
      if (!TURBO_PLATFORM_SET.has(platform)) {
        const comingSoon = (COMING_SOON_PLATFORMS as readonly string[]).includes(platform);
        throw new Error(
          comingSoon
            ? `${platform} sniper is in development — Discord, Roblox, Minecraft, Instagram, TikTok, and Guns.lol are live`
            : `${platform} sniper is not available yet`,
        );
      }
      const result = await startSniper(platform, names, proxies, infinite);
      setStatuses((prev) => {
        const cur = prev[platform] ?? emptySniperStatus(platform);
        return {
          ...prev,
          [platform]: {
            ...cur,
            platform,
            state: "running",
            total_names: result.total_names,
            infinite: result.infinite ?? infinite,
            checks_per_sec: 0,
            valid_checks_per_sec: 0,
            attempt_cps: 0,
            current_target: null,
            // Keep prior captures until the first live poll arrives.
          },
        };
      });
      await refresh();
    },
    [platform, refresh],
  );

  const requestStop = useCallback(async () => {
    setStatuses((prev) => {
      const cur = prev[platform] ?? emptySniperStatus(platform);
      return {
        ...prev,
        [platform]: {
          ...cur,
          state: "idle",
          checks_per_sec: 0,
          valid_checks_per_sec: 0,
          recovery_mode: false,
          current_target: null,
        },
      };
    });
    await stopSniper(platform);
    await refresh();
  }, [platform, refresh]);

  return {
    status,
    statuses,
    clearCaptures,
    requestStart,
    requestStop,
  };
}
