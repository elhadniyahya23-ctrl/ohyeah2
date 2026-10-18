import { apiFetch, parseApiError } from "@/lib/apiClient";

export interface AdminOrder {
  id: number;
  user_id: number;
  username: string | null;
  plan_id: string;
  method: string;
  status: string;
  amount_usd: string;
  currency: string | null;
  tx_hash: string | null;
  sender_wallet: string | null;
  note: string | null;
  created_at: string | null;
}

export interface AdminUser {
  id: number;
  username: string;
  rank: string | null;
  has_active_plan: boolean;
  is_admin: boolean;
  is_trial: boolean;
  can_manage_proxies: boolean;
  plan_expires_at: string | null;
  trial_used_seconds: number;
  trial_limit_seconds: number;
  trial_remaining_seconds: number | null;
  trial_exhausted: boolean;
  registration_ip: string | null;
  last_ip: string | null;
  created_at: string | null;
  has_session: boolean;
}

export interface AdminOverview {
  total_users: number;
  active_paid: number;
  trial_users: number;
  pending_orders: number;
  live_snipers: number;
  admins: string[];
}

export interface AdminLiveSniper {
  user_id: number | null;
  username: string | null;
  rank: string | null;
  last_ip: string | null;
  user_token: string;
  token_prefix?: string | null;
  orphan?: boolean;
  unauthorized?: boolean;
  platform: string;
  state: string;
  progress_pct: number | null;
  checks_done: number | null;
  total_names: number | null;
  checks_per_sec: number | null;
  available: number | null;
  occupied: number | null;
  errors: number | null;
  rate_limits: number | null;
  elapsed_seconds: number | null;
  current_target: string | null;
  vps_pool: string | null;
  node_id: string | null;
  started_at: number | null;
  captures: number;
  trial_remaining_seconds: number | null;
}

export type CleanupSnipersMode = "orphans" | "unauthorized" | "all";

export type GrantPlanId =
  | "premium-1-week"
  | "premium-1-month"
  | "premium-lifetime"
  | "premium-custom";

export type UserPlanFilter = "all" | "paid" | "trial" | "expired" | "admin";

export interface AdminClientProxies {
  user_id: number;
  username: string;
  rank: string | null;
  has_active_plan: boolean;
  can_manage_proxies: boolean;
  proxy_count: number;
  proxies: string[];
}

export async function fetchAdminOrders(status?: string): Promise<AdminOrder[]> {
  const q = status ? `?status=${encodeURIComponent(status)}` : "";
  const res = await apiFetch(`/api/billing/admin/orders${q}`);
  if (!res.ok) await parseApiError(res, "Failed to load orders");
  const data = await res.json();
  return data.orders ?? [];
}

export async function activateAdminOrder(orderId: number): Promise<void> {
  const res = await apiFetch(`/api/billing/admin/activate?order_id=${orderId}`, {
    method: "POST",
  });
  if (!res.ok) await parseApiError(res, "Failed to activate order");
}

export async function rejectAdminOrder(orderId: number): Promise<void> {
  const res = await apiFetch(`/api/billing/admin/reject?order_id=${orderId}`, {
    method: "POST",
  });
  if (!res.ok) await parseApiError(res, "Failed to reject order");
}

export async function fetchAdminOverview(): Promise<AdminOverview> {
  const res = await apiFetch("/api/admin/overview");
  if (!res.ok) await parseApiError(res, "Failed to load overview");
  return res.json();
}

export async function fetchAdminUsers(opts: {
  q?: string;
  plan?: UserPlanFilter;
  limit?: number;
  offset?: number;
}): Promise<{ total: number; users: AdminUser[] }> {
  const params = new URLSearchParams();
  if (opts.q) params.set("q", opts.q);
  if (opts.plan && opts.plan !== "all") params.set("plan", opts.plan);
  params.set("limit", String(opts.limit ?? 50));
  params.set("offset", String(opts.offset ?? 0));
  const res = await apiFetch(`/api/admin/users?${params}`);
  if (!res.ok) await parseApiError(res, "Failed to load users");
  return res.json();
}

export interface AdminUserDetailUser extends AdminUser {
  token: string | null;
  token_prefix: string | null;
  using_trial_proxies: boolean;
  trial_proxy_count: number;
  names_count: number;
  proxy_count: number;
}

export interface AdminUserDetail {
  user: AdminUserDetailUser;
  proxies: string[];
  settings: {
    webhook_url: string;
    webhook_mode: string;
    webhook_user_id: string;
    webhook_bot_username: string;
    webhook_message_template: string;
    webhook_embed_enabled: boolean;
  };
  live_snipers: AdminLiveSniper[];
  all_sniper_sessions: AdminLiveSniper[];
  orders: Array<{
    id: number;
    plan_id: string;
    method: string;
    status: string;
    amount_usd: string | null;
    currency: string | null;
    tx_hash: string | null;
    sender_wallet: string | null;
    note: string | null;
    created_at: string | null;
  }>;
  recent_jobs: Array<{
    id: string;
    platform: string;
    status: string;
    workers: number;
    proxy: string | null;
    webhook_url: string | null;
    targets_count: number | null;
    stats: Record<string, unknown> | null;
    created_at: string | null;
    updated_at: string | null;
  }>;
  recent_hits: Array<{
    id: number;
    job_id: string;
    platform: string;
    target: string;
    status: string;
    created_at: string | null;
  }>;
  audit_logs: AdminAuditLog[];
}

export async function fetchAdminUserDetail(userId: number): Promise<AdminUserDetail> {
  const res = await apiFetch(`/api/admin/users/${userId}`);
  if (!res.ok) await parseApiError(res, "Failed to load user profile");
  return res.json();
}

export async function grantAdminPlan(
  userId: number,
  planId: GrantPlanId,
  durationDays?: number,
): Promise<{ user: AdminUser; granted: string }> {
  const body: { user_id: number; plan_id: GrantPlanId; duration_days?: number } = {
    user_id: userId,
    plan_id: planId,
  };
  if (durationDays != null) {
    body.duration_days = durationDays;
  }
  const res = await apiFetch("/api/admin/users/grant-plan", {
    method: "POST",
    body: JSON.stringify(body),
  });
  if (!res.ok) await parseApiError(res, "Failed to grant plan");
  return res.json();
}

export async function resetAdminTrial(userId: number): Promise<{ user: AdminUser }> {
  const res = await apiFetch("/api/admin/users/reset-trial", {
    method: "POST",
    body: JSON.stringify({ user_id: userId }),
  });
  if (!res.ok) await parseApiError(res, "Failed to reset trial");
  return res.json();
}

export async function expireAdminUser(userId: number): Promise<{ user: AdminUser }> {
  const res = await apiFetch("/api/admin/users/expire", {
    method: "POST",
    body: JSON.stringify({ user_id: userId }),
  });
  if (!res.ok) await parseApiError(res, "Failed to expire user");
  return res.json();
}

export async function deleteAdminUser(
  userId: number,
): Promise<{ ok: boolean; username: string; snipers_stopped: number }> {
  const res = await apiFetch(`/api/admin/users/${userId}`, { method: "DELETE" });
  if (!res.ok) await parseApiError(res, "Failed to delete user");
  return res.json();
}

export async function clearAdminUserProxies(
  userId: number,
): Promise<{ ok: boolean; cleared: number; proxies: string[] }> {
  const res = await apiFetch(`/api/admin/users/${userId}/proxies/clear`, { method: "POST" });
  if (!res.ok) await parseApiError(res, "Failed to clear proxies");
  return res.json();
}

export async function fetchAdminProxies(opts: {
  q?: string;
  limit?: number;
  offset?: number;
}): Promise<{ total: number; clients: AdminClientProxies[] }> {
  const params = new URLSearchParams();
  if (opts.q) params.set("q", opts.q);
  params.set("limit", String(opts.limit ?? 50));
  params.set("offset", String(opts.offset ?? 0));
  const res = await apiFetch(`/api/admin/proxies?${params}`);
  if (!res.ok) await parseApiError(res, "Failed to load client proxies");
  return res.json();
}

export async function fetchAdminSnipers(activeOnly = true): Promise<{
  count: number;
  snipers: AdminLiveSniper[];
}> {
  const res = await apiFetch(`/api/admin/snipers?active_only=${activeOnly ? "true" : "false"}`);
  if (!res.ok) await parseApiError(res, "Failed to load live snipers");
  return res.json();
}

export async function stopAdminSniper(userToken: string, platform: string): Promise<void> {
  const res = await apiFetch("/api/admin/snipers/stop", {
    method: "POST",
    body: JSON.stringify({ user_token: userToken, platform }),
  });
  if (!res.ok) await parseApiError(res, "Failed to stop sniper");
}

export async function cleanupAdminSnipers(
  mode: CleanupSnipersMode = "unauthorized",
): Promise<{ stopped: number; mode: string }> {
  const res = await apiFetch("/api/admin/snipers/cleanup", {
    method: "POST",
    body: JSON.stringify({ mode }),
  });
  if (!res.ok) await parseApiError(res, "Failed to cleanup snipers");
  return res.json();
}

export interface AdminAuditLog {
  id: number;
  actor_id: number | null;
  actor_username: string;
  action: string;
  target_user_id: number | null;
  target_username: string | null;
  detail: string | null;
  meta: Record<string, unknown>;
  actor_ip: string | null;
  created_at: string | null;
}

export async function fetchAdminLogs(opts: {
  q?: string;
  action?: string;
  limit?: number;
  offset?: number;
}): Promise<{ total: number; logs: AdminAuditLog[] }> {
  const params = new URLSearchParams();
  if (opts.q) params.set("q", opts.q);
  if (opts.action) params.set("action", opts.action);
  params.set("limit", String(opts.limit ?? 50));
  params.set("offset", String(opts.offset ?? 0));
  const res = await apiFetch(`/api/admin/logs?${params}`);
  if (!res.ok) await parseApiError(res, "Failed to load admin logs");
  return res.json();
}
