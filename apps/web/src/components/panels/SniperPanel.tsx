"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useAuth } from "@/context/AuthContext";
import { useAuthModal } from "@/context/AuthModalContext";
import { useToast } from "@/context/ToastContext";
import { canManageProxies } from "@/lib/auth";
import { getGlobalNames, getGlobalProxies, setGlobalProxies } from "@/lib/globalStore";
import { fetchNamesCount, NAMES_UPDATED_EVENT } from "@/lib/namesApi";
import { fetchProxies, saveProxies } from "@/lib/proxiesApi";
import type { PlatformId } from "@/lib/platforms";
import type { SniperStatus } from "@/lib/sniperUi";
import { LOCKED_USERNAME_NOTE } from "@/lib/sniperCopy";

interface Props {
  platform: PlatformId;
  platformLabel: string;
  status: SniperStatus;
  onStart: (names: string[], proxies: string[], infinite?: boolean) => Promise<void>;
  onStop: () => Promise<void>;
  onGoNames: () => void;
  onGoProxies: () => void;
}

export function SniperPanel({
  platform,
  platformLabel,
  status,
  onStart,
  onStop,
  onGoNames,
  onGoProxies,
}: Props) {
  const { user } = useAuth();
  const { openAuth } = useAuthModal();
  const { showToast } = useToast();
  const [loading, setLoading] = useState(false);
  const [countsReady, setCountsReady] = useState(false);
  const [selectedCount, setSelectedCount] = useState(0);
  const [proxyCount, setProxyCount] = useState(0);
  const refreshSeq = useRef(0);
  const ownProxies = canManageProxies(user);

  const refreshCounts = useCallback(async () => {
    const seq = ++refreshSeq.current;

    if (user) {
      setCountsReady(false);
      try {
        const namesData = await fetchNamesCount();
        if (seq !== refreshSeq.current) return;
        setSelectedCount(namesData.count);

        if (ownProxies) {
          const proxyData = await fetchProxies().catch(() => ({
            proxies: getGlobalProxies(),
            count: getGlobalProxies().length,
          }));
          if (seq !== refreshSeq.current) return;
          if (proxyData.proxies.length > 0) {
            setGlobalProxies(proxyData.proxies);
            setProxyCount(proxyData.count);
          } else {
            setProxyCount(getGlobalProxies().length);
          }
        } else {
          setProxyCount(0);
        }
      } catch {
        if (seq !== refreshSeq.current) return;
        setProxyCount(ownProxies ? getGlobalProxies().length : 0);
      } finally {
        if (seq === refreshSeq.current) {
          setCountsReady(true);
        }
      }
      return;
    }

    if (seq !== refreshSeq.current) return;
    setProxyCount(0);
    setSelectedCount(getGlobalNames().length);
    setCountsReady(true);
  }, [user, ownProxies]);

  useEffect(() => {
    refreshCounts();
    const onStorage = (e: StorageEvent) => {
      if (e.key === "phantom_global_proxies" || e.key === "phantom_global_names") {
        refreshCounts();
      }
    };
    const onNamesUpdated = (e: Event) => {
      const detail = (e as CustomEvent<{ count?: number }>).detail;
      if (typeof detail?.count === "number") {
        refreshSeq.current += 1;
        setSelectedCount(detail.count);
        setCountsReady(true);
        return;
      }
      refreshCounts();
    };
    window.addEventListener("storage", onStorage);
    window.addEventListener("focus", refreshCounts);
    window.addEventListener(NAMES_UPDATED_EVENT, onNamesUpdated);
    return () => {
      window.removeEventListener("storage", onStorage);
      window.removeEventListener("focus", refreshCounts);
      window.removeEventListener(NAMES_UPDATED_EVENT, onNamesUpdated);
    };
  }, [refreshCounts]);

  const running = status.state === "running" || status.state === "queued";

  const run = async () => {
    if (!user) {
      openAuth("signup", true);
      return;
    }

    let proxies: string[] = [];
    let nameCount = selectedCount;

    try {
      const data = await fetchNamesCount();
      nameCount = data.count;
      setSelectedCount(data.count);
      setCountsReady(true);
    } catch {
      nameCount = selectedCount;
    }

    if (ownProxies) {
      proxies = getGlobalProxies();
      try {
        if (proxies.length > 0) {
          const saved = await saveProxies(proxies);
          setProxyCount(saved.count);
        } else {
          const fromServer = await fetchProxies();
          proxies = fromServer.proxies;
          if (proxies.length > 0) {
            setGlobalProxies(proxies);
          }
          setProxyCount(proxies.length);
        }
      } catch {
        setProxyCount(proxies.length);
      }
    }

    if (!running && nameCount === 0) {
      showToast("Load names first — generate a list in the Names tab", "warning");
      return;
    }

    setLoading(true);
    try {
      if (running) {
        await onStop();
      } else {
        // Trial: empty proxies → API injects shared trial pool
        // Infinite mode is stored from Names panel toggle
        const infinite =
          typeof window !== "undefined" &&
          window.localStorage.getItem("phantom_infinite_list") === "1";
        await onStart([], ownProxies ? proxies : [], infinite);
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Something went wrong";
      showToast(msg, "error");
    } finally {
      setLoading(false);
    }
  };

  const displayCount = Math.max(selectedCount, status.total_names || 0);
  const infiniteOn =
    typeof window !== "undefined" &&
    window.localStorage.getItem("phantom_infinite_list") === "1";
  const trialLeft =
    user?.is_trial && typeof status.trial_remaining_seconds === "number"
      ? status.trial_remaining_seconds
      : user?.is_trial && typeof user.trial_remaining_seconds === "number"
        ? user.trial_remaining_seconds
        : null;

  return (
    <>
      <div className="tab-header">
        <div>
          <h2 className="tab-title">{platformLabel} Sniper</h2>
          <p className="tab-desc-sm">Check username availability in order</p>
          {platform === "tiktok" && (
            <p className="tab-desc-sm" style={{ marginTop: 4, opacity: 0.85 }}>
              {LOCKED_USERNAME_NOTE}
            </p>
          )}
        </div>
      </div>

      <div className="sniper-hero glass-card">
        <h3 className="sniper-engine-title">{platformLabel} Username Engine</h3>
        <p className="sniper-engine-desc">
          {infiniteOn
            ? "Infinite list ON — loops the list forever until you press Stop."
            : "Checks each username once from top to bottom, then stops."}
          {trialLeft != null && (
            <>
              <br />
              Free Trial remaining: {Math.max(0, Math.floor(trialLeft))}s (saved to your account)
            </>
          )}
        </p>

        <div className="sniper-actions">
          {!running ? (
            <button
              type="button"
              className="btn btn-primary btn-glow btn-lg"
              onClick={run}
              disabled={loading || (!countsReady && !!user)}
            >
              <span>
                {loading
                  ? "PLEASE WAIT…"
                  : !countsReady && user
                    ? "LOADING NAMES…"
                    : "START SNIPER"}
              </span>
            </button>
          ) : (
            <button
              type="button"
              className="btn btn-danger btn-lg"
              onClick={run}
              disabled={loading}
            >
              <span>{loading ? "PLEASE WAIT…" : "STOP SNIPER"}</span>
            </button>
          )}
        </div>
      </div>

      <div className="sniper-info glass-card">
        <div className="info-row">
          <span className="info-label">Names loaded</span>
          <span className="info-value mono">{displayCount.toLocaleString()}</span>
        </div>
        <div className="info-row">
          <span className="info-label">Proxies</span>
          <span className="info-value mono">
            {ownProxies ? proxyCount : user?.is_trial ? "Shared (trial)" : "—"}
          </span>
        </div>
        <div className="info-row">
          <span className="info-label">Manage lists</span>
          <span className="info-value" style={{ display: "flex", gap: 8 }}>
            <button
              type="button"
              className="btn btn-outline btn-sm"
              onClick={() => {
                if (!user) {
                  openAuth("signup", true);
                  return;
                }
                onGoNames();
              }}
            >
              Names
            </button>
            {ownProxies && (
              <button type="button" className="btn btn-outline btn-sm" onClick={onGoProxies}>
                Proxies
              </button>
            )}
          </span>
        </div>
      </div>
    </>
  );
}
