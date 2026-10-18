"use client";

import { AnimatedNum, PhantomProgressRing } from "@/components/phantom/PhantomProgressRing";
import { useLiveElapsed } from "@/hooks/useLiveElapsed";
import {
  dashboardStateLabel,
  dashboardStatus,
  formatElapsed,
  type SniperStatus,
} from "@/lib/sniperUi";
import type { PlatformId } from "@/lib/platforms";
import { LOCKED_USERNAME_NOTE } from "@/lib/sniperCopy";

interface Props {
  platform: PlatformId;
  platformLabel: string;
  status: SniperStatus;
}

export function DashboardPanel({ platform, platformLabel, status }: Props) {
  const view = dashboardStatus(status);
  const live = view.state === "running" || view.state === "queued";
  const stateLabel = dashboardStateLabel(view);
  const elapsed = useLiveElapsed(view.elapsed_seconds, live);
  const validChecks = view.available + view.occupied;
  const passChecks =
    view.infinite && view.total_names > 0
      ? view.checks_done % view.total_names
      : view.checks_done;
  const progressPct =
    view.total_names > 0
      ? Math.min(100, (passChecks / view.total_names) * 100)
      : view.progress_pct;
  const progressDetail =
    view.infinite && view.total_names > 0 && view.checks_done >= view.total_names ? (
      <>
        Loop {Math.floor(view.checks_done / view.total_names) + 1} ·{" "}
        <AnimatedNum value={passChecks} /> / <AnimatedNum value={view.total_names} />
      </>
    ) : (
      <>
        <AnimatedNum value={view.checks_done} /> / <AnimatedNum value={view.total_names} />
      </>
    );

  return (
    <>
      <div className="tab-header">
        <div>
          <h2 className="tab-title">Dashboard</h2>
          <p className="tab-desc-sm">
            {platformLabel} Username Sniper — Real-time overview
          </p>
          {platform === "tiktok" && (
            <p className="tab-desc-sm" style={{ marginTop: 4, opacity: 0.85 }}>
              {LOCKED_USERNAME_NOTE}
            </p>
          )}
        </div>
        <div className={`status-pill${live ? " running" : ""}`}>
          <span className="status-dot" />
          <span className="status-text">{stateLabel}</span>
        </div>
      </div>

      {view.recovery_mode && live && (
        <p className="tab-desc-sm" style={{ color: "var(--warning)", marginBottom: "0.75rem" }}>
          Proxy limited — slow checks on this IP. Change proxy country for full speed.
        </p>
      )}

      <div className="stats-row">
        <div className="stat-card glass-card">
          <div className="stat-body">
            <div className="stat-value">
              <AnimatedNum value={view.available} />
            </div>
            <div className="stat-label">Available</div>
          </div>
        </div>
        <div className="stat-card glass-card">
          <div className="stat-body">
            <div className="stat-value">
              <AnimatedNum value={view.occupied} />
            </div>
            <div className="stat-label">Taken</div>
          </div>
        </div>
        <div className="stat-card glass-card">
          <div className="stat-body">
            <div className="stat-value">
              <AnimatedNum value={view.checks_per_sec} decimals={1} duration={250} />
            </div>
            <div className="stat-label">Checks/s</div>
          </div>
        </div>
        <div className="stat-card glass-card">
          <div className="stat-body">
            <div
              className="stat-value"
              style={{ color: view.errors > 0 ? "var(--danger)" : undefined }}
            >
              <AnimatedNum value={view.errors} />
            </div>
            <div className="stat-label">Errors</div>
          </div>
        </div>
      </div>

      <div className="dash-grid">
        <div className="glass-card progress-card">
          <h3 className="card-title">PROGRESS</h3>
          <PhantomProgressRing
            pct={progressPct}
            detail={progressDetail}
          />
          <div className="meta-grid" style={{ gridTemplateColumns: "repeat(4, 1fr)" }}>
            <div className="meta-item">
              <span className="meta-label">ELAPSED</span>
              <span className="meta-value">{formatElapsed(elapsed)}</span>
            </div>
            <div className="meta-item">
              <span className="meta-label">VALID</span>
              <span className="meta-value">
                <AnimatedNum value={validChecks} />
              </span>
            </div>
            <div className="meta-item">
              <span className="meta-label">Rate limits</span>
              <span className="meta-value" style={{ color: "var(--danger)" }}>
                <AnimatedNum value={view.rate_limits} />
              </span>
            </div>
            <div className="meta-item">
              <span className="meta-label">Late proxy</span>
              <span className="meta-value" style={{ color: "var(--warning)" }}>
                <AnimatedNum value={view.proxy_misses} />
              </span>
            </div>
          </div>
        </div>

        <div className="glass-card hits-card">
          <h3 className="card-title">RECENT CAPTURES</h3>
          <div className="hits-list">
            {view.captures.length === 0 ? (
              <div className="hits-empty">
                <span>No captures yet. Start sniping!</span>
              </div>
            ) : (
              [...view.captures].reverse().map((c) => (
                <div key={`${c.name}-${c.at}`} className="hit-item">
                  <span className="hit-name mono">{c.name}</span>
                  <span className="hit-time">{new Date(c.at).toLocaleTimeString()}</span>
                </div>
              ))
            )}
          </div>
        </div>
      </div>

      <div className="glass-card target-bar">
        <span className="target-label">CURRENT TARGET</span>
        <span className="target-name mono">
          {view.current_target
            ? `@${view.current_target}`
            : live
              ? "…"
              : stateLabel === "interrupted"
                ? "Paused — press Start to continue"
                : "Idle"}
        </span>
      </div>
    </>
  );
}
