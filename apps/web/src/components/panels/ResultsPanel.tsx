"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useAuth } from "@/context/AuthContext";
import { useAuthModal } from "@/context/AuthModalContext";
import { useToast } from "@/context/ToastContext";
import { PLATFORMS } from "@/lib/platforms";
import { fetchSavedResults, type SavedResult } from "@/lib/sniperApi";
import type { SniperStatus } from "@/lib/sniperUi";

interface Props {
  statuses: Record<string, SniperStatus>;
  onCleared: () => void;
}

type Row = {
  name: string;
  platform: string;
  platformId: string;
  at: string;
};

export function ResultsPanel({ statuses, onCleared }: Props) {
  const { user } = useAuth();
  const { openAuth } = useAuthModal();
  const { showToast } = useToast();
  const [clearing, setClearing] = useState(false);
  const [saved, setSaved] = useState<SavedResult[]>([]);
  const [loadingSaved, setLoadingSaved] = useState(false);

  const loadSaved = useCallback(async () => {
    if (!user) {
      setSaved([]);
      return;
    }
    setLoadingSaved(true);
    try {
      const rows = await fetchSavedResults(400);
      setSaved(rows);
    } catch {
      /* keep last */
    } finally {
      setLoadingSaved(false);
    }
  }, [user]);

  useEffect(() => {
    void loadSaved();
  }, [loadSaved]);

  // Refresh saved results when live captures grow
  const liveCount = useMemo(
    () => PLATFORMS.reduce((n, p) => n + (statuses[p.id]?.captures?.length || 0), 0),
    [statuses],
  );
  useEffect(() => {
    if (!user) return;
    const t = window.setTimeout(() => void loadSaved(), 800);
    return () => window.clearTimeout(t);
  }, [liveCount, user, loadSaved]);

  const liveRows: Row[] = PLATFORMS.flatMap((p) => {
    const s = statuses[p.id];
    if (!s?.captures?.length) return [];
    return s.captures.map((c) => ({
      name: c.name,
      at: c.at,
      platform: p.label,
      platformId: p.id,
    }));
  });

  const labelById = useMemo(
    () => Object.fromEntries(PLATFORMS.map((p) => [p.id, p.label])),
    [],
  );

  const savedRows: Row[] = saved.map((r) => ({
    name: r.name,
    at: r.at || "",
    platform: labelById[r.platform] || r.platform,
    platformId: r.platform,
  }));

  // Merge live + DB, de-dupe by platform+name+at
  const allCaptures = useMemo(() => {
    const map = new Map<string, Row>();
    for (const row of [...savedRows, ...liveRows]) {
      const key = `${row.platformId}|${row.name}|${row.at}`;
      map.set(key, row);
    }
    return Array.from(map.values()).sort(
      (a, b) => new Date(b.at || 0).getTime() - new Date(a.at || 0).getTime(),
    );
  }, [savedRows, liveRows]);

  const handleClear = async () => {
    if (!user) {
      openAuth("signup", true);
      return;
    }
    setClearing(true);
    try {
      await onCleared();
      setSaved([]);
      showToast("Results cleared", "info");
    } catch {
      showToast("Failed to clear results", "error");
    } finally {
      setClearing(false);
    }
  };

  if (!user) {
    return (
      <>
        <div className="tab-header">
          <div>
            <h2 className="tab-title">Results</h2>
            <p className="tab-desc-sm">Sign up to start sniping and see captures here.</p>
          </div>
        </div>
        <div className="glass-card" style={{ padding: 24 }}>
          <button type="button" className="btn btn-primary" onClick={() => openAuth("signup", true)}>
            Create account
          </button>
        </div>
      </>
    );
  }

  return (
    <>
      <div className="tab-header">
        <div>
          <h2 className="tab-title">Results</h2>
          <p className="tab-desc-sm">
            Available usernames found — saved permanently until you clear them.
          </p>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <div className="count-pill glass-card">
            <span>{allCaptures.length}</span> hits
          </div>
          <button
            type="button"
            className="btn btn-outline btn-sm"
            onClick={() => void loadSaved()}
            disabled={loadingSaved}
          >
            {loadingSaved ? "…" : "Refresh"}
          </button>
          <button
            type="button"
            className="btn btn-outline btn-sm"
            onClick={handleClear}
            disabled={clearing || allCaptures.length === 0}
          >
            {clearing ? "Clearing…" : "Clear"}
          </button>
        </div>
      </div>

      <div className="glass-card hits-card">
        <h3 className="card-title">ALL CAPTURES</h3>
        <div className="hits-list">
          {allCaptures.length === 0 ? (
            <div className="hits-empty">
              <span>No results yet. Start a sniper to find available usernames.</span>
            </div>
          ) : (
            allCaptures.map((c) => (
              <div key={`${c.platformId}-${c.name}-${c.at}`} className="hit-item">
                <span className="hit-name mono">{c.name}</span>
                <span className="hit-time">
                  {c.platform} · {c.at ? new Date(c.at).toLocaleString() : "—"}
                </span>
              </div>
            ))
          )}
        </div>
      </div>
    </>
  );
}
