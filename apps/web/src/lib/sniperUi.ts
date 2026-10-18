import type { PlatformId } from "@/lib/platforms";

export interface SniperCapture {
  name: string;
  at: string;
}

export interface SniperStatus {
  platform: string;
  state: string;
  progress_pct: number;
  checks_done: number;
  total_names: number;
  checks_per_sec: number;
  valid_checks_per_sec: number;
  attempt_cps: number;
  recovery_mode: boolean;
  degrade_reason?: string | null;
  available: number;
  occupied: number;
  errors: number;
  rate_limits: number;
  proxy_misses: number;
  elapsed_seconds: number;
  current_target: string | null;
  last_proxy_error?: string | null;
  captures: SniperCapture[];
  trial_remaining_seconds?: number | null;
  trial_exhausted?: boolean;
  redirect_to_payment?: boolean;
  infinite?: boolean;
  queue_position?: number | null;
  queue_total?: number | null;
}

export function emptySniperStatus(platform: PlatformId | string): SniperStatus {
  return {
    platform,
    state: "idle",
    progress_pct: 0,
    checks_done: 0,
    total_names: 0,
    checks_per_sec: 0,
    valid_checks_per_sec: 0,
    attempt_cps: 0,
    recovery_mode: false,
    degrade_reason: null,
    available: 0,
    occupied: 0,
    errors: 0,
    rate_limits: 0,
    proxy_misses: 0,
    elapsed_seconds: 0,
    current_target: null,
    captures: [],
    trial_remaining_seconds: null,
    trial_exhausted: false,
    redirect_to_payment: false,
  };
}

export function formatElapsed(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  return [h, m, s].map((n) => String(n).padStart(2, "0")).join(":");
}

/** Infer late vs rate-limit degrade even if API omits degrade_reason. */
export function resolveDegradeReason(
  status: SniperStatus,
): "late" | "rate_limit" | null {
  const done = status.checks_done || 0;
  const rl = status.rate_limits || 0;
  const late = status.proxy_misses || 0;
  const err = status.errors || 0;
  const attempts = done + rl + late + err;
  const cps = status.checks_per_sec || 0;
  // Valid checks flowing — do not scare the user with a fail banner.
  if (cps >= 1.0 && done >= 5) {
    return null;
  }
  if (status.degrade_reason === "rate_limit" || status.degrade_reason === "late") {
    if (cps >= 1.0) return null;
    return status.degrade_reason;
  }
  if (attempts < 40 || cps >= 1.5) {
    if (!status.recovery_mode || cps >= 1.0) return null;
    if (status.degrade_reason === "rate_limit" || (rl > late && rl >= 10)) {
      return "rate_limit";
    }
    return "late";
  }
  const lateRatio = late / attempts;
  const rlRatio = rl / attempts;
  const errRatio = err / attempts;
  // Prefer Discord RL over "proxies failing" when rate limits dominate.
  if (rl >= 15 && rlRatio >= 0.3 && rlRatio >= lateRatio) {
    return "rate_limit";
  }
  if (status.recovery_mode || lateRatio >= 0.5 || errRatio >= 0.7) {
    if (rl >= 20 && rlRatio >= 0.35 && rlRatio >= lateRatio && rlRatio >= errRatio) {
      return "rate_limit";
    }
    if (lateRatio >= 0.5 || errRatio >= 0.7) return "late";
  }
  return null;
}

export function dashboardStateLabel(status: SniperStatus): string {
  if (status.state === "queued") {
    // Legacy queued payloads — never show a "waiting list" to users.
    return "starting";
  }
  if (status.state === "running") {
    const active =
      status.checks_done > 0 ||
      status.proxy_misses > 0 ||
      status.rate_limits > 0 ||
      status.errors > 0 ||
      status.available > 0 ||
      status.occupied > 0;
    if (!active) return "starting";
    const reason = resolveDegradeReason(status);
    if (reason === "rate_limit") return "proxy limited";
    if (reason === "late") return "proxies failing";
    return "running";
  }
  if (status.state === "interrupted") return "interrupted";
  if (status.state === "stopped") return "stopped";
  if (status.state === "completed") return "completed";
  return "idle";
}

export function degradeBannerText(status: SniperStatus): string | null {
  const reason = resolveDegradeReason(status);
  if (!reason) return null;
  if (reason === "rate_limit") {
    return "Discord is rate-limiting — keep going, IPs rotate every request.";
  }
  const hint = status.last_proxy_error || "";
  if (hint) {
    return `Checks failing: ${hint.slice(0, 120)}`;
  }
  return "Checks failing — verify your proxy lines.";
}

/** Soften live metrics when idle — never wipe captures from the last run. */
export function dashboardStatus(status: SniperStatus): SniperStatus {
  if (status.state === "running" || status.state === "queued") {
    return status;
  }
  return {
    ...status,
    state: status.state === "completed" ? "completed" : "idle",
    checks_per_sec: 0,
    valid_checks_per_sec: 0,
    attempt_cps: 0,
    recovery_mode: false,
    degrade_reason: null,
    current_target: null,
    // Keep captures / available / checks_done so the dashboard does not "reset".
  };
}
