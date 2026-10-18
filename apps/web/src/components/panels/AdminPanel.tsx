"use client";

import { useCallback, useEffect, useMemo, useState, type FormEvent, type ReactNode } from "react";
import { useAuth } from "@/context/AuthContext";
import { useToast } from "@/context/ToastContext";
import {
  activateAdminOrder,
  cleanupAdminSnipers,
  clearAdminUserProxies,
  deleteAdminUser,
  expireAdminUser,
  fetchAdminOrders,
  fetchAdminOverview,
  fetchAdminProxies,
  fetchAdminLogs,
  fetchAdminSnipers,
  fetchAdminUserDetail,
  fetchAdminUsers,
  grantAdminPlan,
  rejectAdminOrder,
  resetAdminTrial,
  stopAdminSniper,
  type AdminAuditLog,
  type AdminClientProxies,
  type AdminLiveSniper,
  type AdminOrder,
  type AdminOverview,
  type AdminUser,
  type AdminUserDetail,
  type GrantPlanId,
  type UserPlanFilter,
} from "@/lib/adminApi";

type AdminPanelId = "hub" | "users" | "snipers" | "payments" | "proxies" | "logs";
type ProfileSection =
  | "account"
  | "network"
  | "proxies"
  | "snipers"
  | "jobs"
  | "hits"
  | "payments"
  | "logs";
type OrderFilter = "pending_review" | "awaiting_payment" | "completed" | "rejected" | "all";

const ACTION_LABELS: Record<string, string> = {
  grant_plan: "Grant plan",
  set_rank: "Set rank",
  reset_trial: "Reset trial",
  reset_all_trials: "Reset all trials",
  clear_registration_ip: "Clear signup IP",
  expire_user: "Expire user",
  delete_user: "Delete user",
  stop_sniper: "Stop sniper",
  cleanup_snipers: "Cleanup snipers",
  activate_order: "Activate payment",
  reject_order: "Reject payment",
  clear_proxies: "Clear proxies",
};

const HUB_CARDS: {
  id: Exclude<AdminPanelId, "hub">;
  title: string;
  desc: string;
  badgeKey?: keyof AdminOverview;
  hotWhenPositive?: boolean;
}[] = [
  {
    id: "users",
    title: "Accounts",
    desc: "Find a user, open their profile, grant or expire plans.",
    badgeKey: "total_users",
  },
  {
    id: "snipers",
    title: "Live snipers",
    desc: "Watch active jobs, force-stop, kill orphans.",
    badgeKey: "live_snipers",
    hotWhenPositive: true,
  },
  {
    id: "payments",
    title: "Payments",
    desc: "Review pending crypto orders and activate plans.",
    badgeKey: "pending_orders",
    hotWhenPositive: true,
  },
  {
    id: "proxies",
    title: "Proxies",
    desc: "Inspect custom proxy lists uploaded by paid clients.",
  },
  {
    id: "logs",
    title: "Audit logs",
    desc: "Read-only trail of every admin action.",
  },
];

function actionLabel(action: string): string {
  return ACTION_LABELS[action] || action.replace(/_/g, " ");
}

function rankClass(user: AdminUser): string {
  if (user.is_admin) return "admin";
  if (user.trial_exhausted || (user.rank || "").toLowerCase().includes("expired")) return "expired";
  if (user.is_trial) return "trial";
  if (user.has_active_plan) return "paid";
  return "";
}

function fmtElapsed(seconds: number | null | undefined): string {
  const s = Math.max(0, Math.floor(seconds || 0));
  const m = Math.floor(s / 60);
  const r = s % 60;
  return `${m}:${String(r).padStart(2, "0")}`;
}

function fmtDate(value: string | null | undefined): string {
  if (!value) return "—";
  try {
    return new Date(value).toLocaleString();
  } catch {
    return value;
  }
}

async function copyText(value: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(value);
    return true;
  } catch {
    try {
      const ta = document.createElement("textarea");
      ta.value = value;
      ta.setAttribute("readonly", "");
      ta.style.position = "fixed";
      ta.style.left = "-9999px";
      document.body.appendChild(ta);
      ta.select();
      const ok = document.execCommand("copy");
      document.body.removeChild(ta);
      return ok;
    } catch {
      return false;
    }
  }
}

function PanelShell({
  title,
  desc,
  onBack,
  tools,
  children,
}: {
  title: string;
  desc: string;
  onBack: () => void;
  tools?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="admin-panel-shell">
      <div className="admin-panel-head">
        <div className="admin-panel-head-main">
          <div className="admin-panel-kicker">
            <button type="button" className="admin-back" onClick={onBack}>
              ← Admin home
            </button>
          </div>
          <h2 className="admin-panel-title">{title}</h2>
          <p className="admin-panel-desc">{desc}</p>
        </div>
        {tools ? <div className="admin-panel-tools">{tools}</div> : null}
      </div>
      {children}
    </div>
  );
}

export function AdminPanel() {
  const { user } = useAuth();
  const { showToast } = useToast();
  const [panel, setPanel] = useState<AdminPanelId>("hub");

  const [overview, setOverview] = useState<AdminOverview | null>(null);
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [userTotal, setUserTotal] = useState(0);
  const [userQuery, setUserQuery] = useState("");
  const [searchInput, setSearchInput] = useState("");
  const [planFilter, setPlanFilter] = useState<UserPlanFilter>("all");
  const [userOffset, setUserOffset] = useState(0);
  const userLimit = 50;

  const [snipers, setSnipers] = useState<AdminLiveSniper[]>([]);
  const [orders, setOrders] = useState<AdminOrder[]>([]);
  const [orderFilter, setOrderFilter] = useState<OrderFilter>("pending_review");

  const [proxies, setProxies] = useState<AdminClientProxies[]>([]);
  const [proxyTotal, setProxyTotal] = useState(0);
  const [proxyQuery, setProxyQuery] = useState("");
  const [proxySearchInput, setProxySearchInput] = useState("");
  const [proxyOffset, setProxyOffset] = useState(0);
  const [expandedProxyUser, setExpandedProxyUser] = useState<number | null>(null);
  const proxyLimit = 50;

  const [logs, setLogs] = useState<AdminAuditLog[]>([]);
  const [logTotal, setLogTotal] = useState(0);
  const [logQuery, setLogQuery] = useState("");
  const [logSearchInput, setLogSearchInput] = useState("");
  const [logActionFilter, setLogActionFilter] = useState("");
  const [logOffset, setLogOffset] = useState(0);
  const logLimit = 50;

  const [selectedUserId, setSelectedUserId] = useState<number | null>(null);
  const [userDetail, setUserDetail] = useState<AdminUserDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [profileSection, setProfileSection] = useState<ProfileSection>("account");

  const [loading, setLoading] = useState(false);
  const [busyKey, setBusyKey] = useState<string | null>(null);

  const isAdmin = Boolean(user?.is_admin);

  const loadOverview = useCallback(async () => {
    const data = await fetchAdminOverview();
    setOverview(data);
  }, []);

  const loadUsers = useCallback(async () => {
    const data = await fetchAdminUsers({
      q: userQuery || undefined,
      plan: planFilter,
      limit: userLimit,
      offset: userOffset,
    });
    setUsers(data.users);
    setUserTotal(data.total);
  }, [userQuery, planFilter, userOffset]);

  const loadSnipers = useCallback(async () => {
    const data = await fetchAdminSnipers(true);
    setSnipers(data.snipers);
  }, []);

  const loadOrders = useCallback(async () => {
    const data = await fetchAdminOrders(orderFilter === "all" ? undefined : orderFilter);
    setOrders(data);
  }, [orderFilter]);

  const loadProxies = useCallback(async () => {
    const data = await fetchAdminProxies({
      q: proxyQuery || undefined,
      limit: proxyLimit,
      offset: proxyOffset,
    });
    setProxies(data.clients);
    setProxyTotal(data.total);
  }, [proxyQuery, proxyOffset]);

  const loadLogs = useCallback(async () => {
    const data = await fetchAdminLogs({
      q: logQuery || undefined,
      action: logActionFilter || undefined,
      limit: logLimit,
      offset: logOffset,
    });
    setLogs(data.logs);
    setLogTotal(data.total);
  }, [logQuery, logActionFilter, logOffset]);

  const loadUserDetail = useCallback(
    async (userId: number) => {
      setDetailLoading(true);
      try {
        const data = await fetchAdminUserDetail(userId);
        setUserDetail(data);
      } catch (err) {
        showToast(err instanceof Error ? err.message : "Failed to load profile", "error");
        setSelectedUserId(null);
        setUserDetail(null);
      } finally {
        setDetailLoading(false);
      }
    },
    [showToast],
  );

  const openUserProfile = useCallback(
    (userId: number) => {
      setSelectedUserId(userId);
      setUserDetail(null);
      setProfileSection("account");
      void loadUserDetail(userId);
    },
    [loadUserDetail],
  );

  const closeUserProfile = useCallback(() => {
    setSelectedUserId(null);
    setUserDetail(null);
  }, []);

  const goHome = useCallback(() => {
    closeUserProfile();
    setPanel("hub");
  }, [closeUserProfile]);

  const refresh = useCallback(async () => {
    if (!isAdmin) return;
    if (selectedUserId != null) {
      await loadUserDetail(selectedUserId);
      return;
    }
    setLoading(true);
    try {
      if (panel === "hub") {
        await Promise.all([loadOverview(), loadSnipers()]);
      } else if (panel === "users") {
        await loadUsers();
      } else if (panel === "snipers") {
        await loadSnipers();
      } else if (panel === "proxies") {
        await loadProxies();
      } else if (panel === "logs") {
        await loadLogs();
      } else if (panel === "payments") {
        await loadOrders();
      }
    } catch (err) {
      showToast(err instanceof Error ? err.message : "Failed to load admin data", "error");
    } finally {
      setLoading(false);
    }
  }, [
    isAdmin,
    selectedUserId,
    panel,
    loadOverview,
    loadUsers,
    loadSnipers,
    loadOrders,
    loadProxies,
    loadLogs,
    loadUserDetail,
    showToast,
  ]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    if (selectedUserId != null) return;
    if (panel !== "snipers" && panel !== "hub") return;
    const id = window.setInterval(() => {
      void loadSnipers().catch(() => undefined);
      if (panel === "hub") void loadOverview().catch(() => undefined);
    }, 8000);
    return () => window.clearInterval(id);
  }, [panel, selectedUserId, loadSnipers, loadOverview]);

  useEffect(() => {
    if (selectedUserId == null) return;
    const id = window.setInterval(() => {
      void loadUserDetail(selectedUserId).catch(() => undefined);
    }, 10000);
    return () => window.clearInterval(id);
  }, [selectedUserId, loadUserDetail]);

  const pageLabel = useMemo(() => {
    const start = userTotal === 0 ? 0 : userOffset + 1;
    const end = Math.min(userOffset + userLimit, userTotal);
    return `${start}–${end} of ${userTotal}`;
  }, [userOffset, userTotal]);

  const proxyPageLabel = useMemo(() => {
    const start = proxyTotal === 0 ? 0 : proxyOffset + 1;
    const end = Math.min(proxyOffset + proxyLimit, proxyTotal);
    return `${start}–${end} of ${proxyTotal}`;
  }, [proxyOffset, proxyTotal]);

  const logPageLabel = useMemo(() => {
    const start = logTotal === 0 ? 0 : logOffset + 1;
    const end = Math.min(logOffset + logLimit, logTotal);
    return `${start}–${end} of ${logTotal}`;
  }, [logOffset, logTotal]);

  if (!isAdmin) {
    return (
      <>
        <div className="tab-header">
          <h2 className="tab-title">Admin</h2>
        </div>
        <p className="auth-loading">Access denied.</p>
      </>
    );
  }

  const runAction = async (key: string, fn: () => Promise<void>, okMsg: string) => {
    setBusyKey(key);
    try {
      await fn();
      showToast(okMsg, "success");
      await refresh();
    } catch (err) {
      showToast(err instanceof Error ? err.message : "Action failed", "error");
    } finally {
      setBusyKey(null);
    }
  };

  const onSearch = (e: FormEvent) => {
    e.preventDefault();
    setUserOffset(0);
    setUserQuery(searchInput.trim());
  };

  const onProxySearch = (e: FormEvent) => {
    e.preventDefault();
    setProxyOffset(0);
    setProxyQuery(proxySearchInput.trim());
  };

  const onLogSearch = (e: FormEvent) => {
    e.preventDefault();
    setLogOffset(0);
    setLogQuery(logSearchInput.trim());
  };

  const refreshBtn = (
    <button type="button" className="btn btn-outline btn-sm" onClick={() => void refresh()}>
      {loading ? "Refreshing…" : "Refresh"}
    </button>
  );

  return (
    <div className="admin-page">
      {selectedUserId != null ? (
        <UserProfilePage
          detail={userDetail}
          loading={detailLoading}
          busyKey={busyKey}
          section={profileSection}
          onSection={setProfileSection}
          onBack={closeUserProfile}
          onRefresh={() => void refresh()}
          onCopy={async (value, label) => {
            const ok = await copyText(value);
            showToast(ok ? `Copied ${label}` : "Copy failed", ok ? "success" : "error");
          }}
          onStopSniper={(token, platform) =>
            void runAction(
              `stop-${token}-${platform}`,
              async () => stopAdminSniper(token, platform),
              `Stopped ${platform}`,
            )
          }
          onGrant={(planId, durationDays) => {
            if (!userDetail) return;
            void runAction(
              `grant-${userDetail.user.id}-${planId}-${durationDays ?? "default"}`,
              async () => {
                await grantAdminPlan(userDetail.user.id, planId, durationDays);
              },
              durationDays
                ? `Granted ${durationDays}d Premium to ${userDetail.user.username}`
                : `Granted ${planId} to ${userDetail.user.username}`,
            );
          }}
          onResetTrial={() => {
            if (!userDetail) return;
            void runAction(
              `trial-${userDetail.user.id}`,
              async () => {
                await resetAdminTrial(userDetail.user.id);
              },
              `Reset trial for ${userDetail.user.username}`,
            );
          }}
          onExpire={() => {
            if (!userDetail) return;
            void runAction(
              `expire-${userDetail.user.id}`,
              async () => {
                await expireAdminUser(userDetail.user.id);
              },
              `Expired ${userDetail.user.username}`,
            );
          }}
          onClearProxies={() => {
            if (!userDetail) return;
            if (
              !window.confirm(
                `Clear all custom proxies for "${userDetail.user.username}"? They will need to paste a new list.`,
              )
            ) {
              return;
            }
            void runAction(
              `clear-proxies-${userDetail.user.id}`,
              async () => {
                await clearAdminUserProxies(userDetail.user.id);
              },
              `Cleared proxies for ${userDetail.user.username}`,
            );
          }}
          onDelete={() => {
            if (!userDetail) return;
            if (
              !window.confirm(
                `Delete account "${userDetail.user.username}" permanently? This removes all data and cannot be undone.`,
              )
            ) {
              return;
            }
            void runAction(
              `delete-${userDetail.user.id}`,
              async () => {
                await deleteAdminUser(userDetail.user.id);
                closeUserProfile();
              },
              `Deleted ${userDetail.user.username}`,
            );
          }}
        />
      ) : panel === "hub" ? (
        <>
          <div className="admin-hero">
            <h2>Admin</h2>
            <p>
              Pick one panel. Everything else stays out of the way —{" "}
              {overview?.admins?.join(" · ") || "asiopitos · eya"} only.
            </p>
          </div>

          <div className="admin-hub-pulse">
            <div className="admin-hub-pulse-item">
              <span>Sniping now</span>
              <strong>{overview?.live_snipers ?? snipers.length}</strong>
            </div>
            <div className="admin-hub-pulse-item">
              <span>Pending pay</span>
              <strong>{overview?.pending_orders ?? "—"}</strong>
            </div>
            <div className="admin-hub-pulse-item">
              <span>Accounts</span>
              <strong>{overview?.total_users ?? "—"}</strong>
            </div>
          </div>

          <div className="admin-hub-grid">
            {HUB_CARDS.map((card) => {
              const badge =
                card.badgeKey && overview ? Number(overview[card.badgeKey] ?? 0) : null;
              const hot = Boolean(card.hotWhenPositive && badge && badge > 0);
              return (
                <button
                  key={card.id}
                  type="button"
                  className="admin-hub-card"
                  onClick={() => setPanel(card.id)}
                >
                  <div className="admin-hub-card-top">
                    <h3 className="admin-hub-card-title">{card.title}</h3>
                    {badge != null && (
                      <span className={`admin-hub-card-badge${hot ? " hot" : ""}`}>{badge}</span>
                    )}
                  </div>
                  <p className="admin-hub-card-desc">{card.desc}</p>
                </button>
              );
            })}
          </div>

          <div className="admin-panel-tools" style={{ marginTop: 18 }}>
            {refreshBtn}
          </div>
        </>
      ) : panel === "users" ? (
        <PanelShell
          title="Accounts"
          desc="Search and open a profile. Grants and deletes live inside the profile."
          onBack={goHome}
          tools={refreshBtn}
        >
          <form className="admin-toolbar" onSubmit={onSearch}>
            <input
              className="admin-search"
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              placeholder="Search username or IP…"
            />
            <button type="submit" className="btn btn-primary btn-sm">
              Search
            </button>
            <div className="admin-chip-row">
              {(
                [
                  ["all", "All"],
                  ["paid", "Paid"],
                  ["trial", "Trial"],
                  ["expired", "Expired"],
                  ["admin", "Admins"],
                ] as const
              ).map(([value, label]) => (
                <button
                  key={value}
                  type="button"
                  className={`btn btn-sm ${planFilter === value ? "btn-primary" : "btn-outline"}`}
                  onClick={() => {
                    setPlanFilter(value);
                    setUserOffset(0);
                  }}
                >
                  {label}
                </button>
              ))}
            </div>
          </form>

          {loading && users.length === 0 ? (
            <p className="auth-loading">Loading accounts…</p>
          ) : users.length === 0 ? (
            <p className="admin-empty">No accounts match.</p>
          ) : (
            <div className="admin-table-wrap">
              <table className="admin-table admin-table-compact">
                <thead>
                  <tr>
                    <th>User</th>
                    <th>Plan</th>
                    <th>Last IP</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {users.map((u) => (
                    <tr key={u.id}>
                      <td>
                        <button
                          type="button"
                          className="admin-user-link"
                          onClick={() => openUserProfile(u.id)}
                        >
                          <div className="admin-user-name">{u.username}</div>
                          <div className="admin-muted">#{u.id}</div>
                        </button>
                      </td>
                      <td>
                        <span className={`admin-rank ${rankClass(u)}`}>{u.rank || "—"}</span>
                      </td>
                      <td>
                        <div className="admin-mono">{u.last_ip || "—"}</div>
                      </td>
                      <td>
                        <div className="admin-account-row-actions">
                          <button
                            type="button"
                            className="btn btn-primary btn-sm"
                            onClick={() => openUserProfile(u.id)}
                          >
                            Open
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <div className="admin-pager">
            <span>{pageLabel}</span>
            <div style={{ display: "flex", gap: 8 }}>
              <button
                type="button"
                className="btn btn-outline btn-sm"
                disabled={userOffset <= 0}
                onClick={() => setUserOffset((v) => Math.max(0, v - userLimit))}
              >
                Prev
              </button>
              <button
                type="button"
                className="btn btn-outline btn-sm"
                disabled={userOffset + userLimit >= userTotal}
                onClick={() => setUserOffset((v) => v + userLimit)}
              >
                Next
              </button>
            </div>
          </div>
        </PanelShell>
      ) : panel === "proxies" ? (
        <PanelShell
          title="Proxies"
          desc="Custom proxy lists from paid clients. Copy or open the account."
          onBack={goHome}
          tools={refreshBtn}
        >
          <form className="admin-toolbar" onSubmit={onProxySearch}>
            <input
              className="admin-search"
              value={proxySearchInput}
              onChange={(e) => setProxySearchInput(e.target.value)}
              placeholder="Search client username…"
            />
            <button type="submit" className="btn btn-primary btn-sm">
              Search
            </button>
          </form>

          {loading && proxies.length === 0 ? (
            <p className="auth-loading">Loading client proxies…</p>
          ) : proxies.length === 0 ? (
            <p className="admin-empty">No paid clients with custom proxies found.</p>
          ) : (
            <div className="admin-table-wrap">
              <table className="admin-table admin-table-compact">
                <thead>
                  <tr>
                    <th>Client</th>
                    <th>Plan</th>
                    <th>Count</th>
                    <th>List</th>
                  </tr>
                </thead>
                <tbody>
                  {proxies.map((c) => (
                    <tr key={c.user_id}>
                      <td>
                        <button
                          type="button"
                          className="admin-user-link"
                          onClick={() => openUserProfile(c.user_id)}
                        >
                          <div className="admin-user-name">{c.username}</div>
                          <div className="admin-muted">#{c.user_id}</div>
                        </button>
                      </td>
                      <td>
                        <span
                          className={`admin-rank ${c.has_active_plan ? "paid" : "expired"}`}
                        >
                          {c.rank || "—"}
                        </span>
                      </td>
                      <td>
                        <strong>{c.proxy_count}</strong>
                      </td>
                      <td>
                        {c.proxy_count === 0 ? (
                          <span className="admin-muted">None</span>
                        ) : (
                          <>
                            <div className="admin-proxy-actions">
                              <button
                                type="button"
                                className="btn btn-outline btn-sm"
                                onClick={() =>
                                  setExpandedProxyUser((prev) =>
                                    prev === c.user_id ? null : c.user_id,
                                  )
                                }
                              >
                                {expandedProxyUser === c.user_id ? "Hide" : "Show"}
                              </button>
                              <button
                                type="button"
                                className="btn btn-primary btn-sm"
                                onClick={() => {
                                  void (async () => {
                                    const ok = await copyText(c.proxies.join("\n"));
                                    showToast(
                                      ok
                                        ? `Copied ${c.proxy_count} prox${c.proxy_count === 1 ? "y" : "ies"} (${c.username})`
                                        : "Could not copy proxies",
                                      ok ? "success" : "error",
                                    );
                                  })();
                                }}
                              >
                                Copy all
                              </button>
                            </div>
                            {expandedProxyUser === c.user_id && (
                              <div className="admin-proxy-list">
                                {c.proxies.map((line, idx) => (
                                  <div
                                    key={`${c.user_id}-${idx}`}
                                    className="admin-proxy-row"
                                  >
                                    <code className="admin-mono">{line}</code>
                                    <button
                                      type="button"
                                      className="btn btn-outline btn-sm admin-proxy-copy"
                                      title="Copy proxy"
                                      onClick={() => {
                                        void (async () => {
                                          const ok = await copyText(line);
                                          showToast(
                                            ok ? "Proxy copied" : "Could not copy",
                                            ok ? "success" : "error",
                                          );
                                        })();
                                      }}
                                    >
                                      Copy
                                    </button>
                                  </div>
                                ))}
                              </div>
                            )}
                          </>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <div className="admin-pager">
            <span>{proxyPageLabel}</span>
            <div style={{ display: "flex", gap: 8 }}>
              <button
                type="button"
                className="btn btn-outline btn-sm"
                disabled={proxyOffset <= 0}
                onClick={() => setProxyOffset((v) => Math.max(0, v - proxyLimit))}
              >
                Prev
              </button>
              <button
                type="button"
                className="btn btn-outline btn-sm"
                disabled={proxyOffset + proxyLimit >= proxyTotal}
                onClick={() => setProxyOffset((v) => v + proxyLimit)}
              >
                Next
              </button>
            </div>
          </div>
        </PanelShell>
      ) : panel === "snipers" ? (
        <PanelShell
          title="Live snipers"
          desc={`Auto-refreshes every 8s · ${snipers.length} active`}
          onBack={goHome}
          tools={
            <>
              {refreshBtn}
              <button
                type="button"
                className="btn btn-outline btn-sm"
                disabled={!!busyKey}
                onClick={() =>
                  void (async () => {
                    setBusyKey("cleanup-unauthorized");
                    try {
                      const r = await cleanupAdminSnipers("unauthorized");
                      showToast(
                        r.stopped
                          ? `Killed ${r.stopped} orphan/expired session(s)`
                          : "No orphan or expired sessions",
                        "success",
                      );
                      await refresh();
                    } catch (err) {
                      showToast(err instanceof Error ? err.message : "Cleanup failed", "error");
                    } finally {
                      setBusyKey(null);
                    }
                  })()
                }
              >
                {busyKey === "cleanup-unauthorized" ? "Killing…" : "Kill orphans"}
              </button>
              <button
                type="button"
                className="btn btn-outline btn-sm"
                disabled={!!busyKey}
                onClick={() =>
                  void (async () => {
                    setBusyKey("cleanup-all");
                    try {
                      const r = await cleanupAdminSnipers("all");
                      showToast(
                        r.stopped ? `Killed ${r.stopped} session(s)` : "No live sessions",
                        "success",
                      );
                      await refresh();
                    } catch (err) {
                      showToast(err instanceof Error ? err.message : "Kill all failed", "error");
                    } finally {
                      setBusyKey(null);
                    }
                  })()
                }
              >
                {busyKey === "cleanup-all" ? "Killing…" : "Kill all"}
              </button>
            </>
          }
        >
          {snipers.length === 0 ? (
            <p className="admin-empty">No active snipers.</p>
          ) : (
            <div className="admin-sniper-grid">
              {snipers.map((s) => (
                <SniperCard
                  key={`${s.user_token}-${s.platform}`}
                  sniper={s}
                  busy={busyKey === `stop-${s.user_token}-${s.platform}`}
                  onOpen={s.user_id != null ? () => openUserProfile(s.user_id!) : undefined}
                  onStop={() =>
                    void runAction(
                      `stop-${s.user_token}-${s.platform}`,
                      async () => stopAdminSniper(s.user_token, s.platform),
                      `Stopped ${s.username ?? "user"} / ${s.platform}`,
                    )
                  }
                />
              ))}
            </div>
          )}
        </PanelShell>
      ) : panel === "payments" ? (
        <PanelShell
          title="Payments"
          desc="Activate or reject orders. One filter at a time."
          onBack={goHome}
          tools={refreshBtn}
        >
          <div className="admin-toolbar">
            <div className="admin-chip-row">
              {(
                [
                  ["pending_review", "Pending"],
                  ["awaiting_payment", "Awaiting"],
                  ["completed", "Completed"],
                  ["rejected", "Rejected"],
                  ["all", "All"],
                ] as const
              ).map(([value, label]) => (
                <button
                  key={value}
                  type="button"
                  className={`btn btn-sm ${orderFilter === value ? "btn-primary" : "btn-outline"}`}
                  onClick={() => setOrderFilter(value)}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>

          {loading && orders.length === 0 ? (
            <p className="auth-loading">Loading orders…</p>
          ) : orders.length === 0 ? (
            <p className="admin-empty">No orders in this filter.</p>
          ) : (
            <div className="admin-order-list">
              {orders.map((o) => (
                <div key={o.id} className="admin-order-card">
                  <div className="admin-order-head">
                    <div>
                      <strong>#{o.id}</strong> ·{" "}
                      <button
                        type="button"
                        className="admin-user-link"
                        style={{ display: "inline" }}
                        onClick={() => openUserProfile(o.user_id)}
                      >
                        <span className="admin-user-name" style={{ display: "inline" }}>
                          {o.username ?? `user ${o.user_id}`}
                        </span>
                      </button>{" "}
                      · {o.plan_id}
                    </div>
                    <span className="ph-status-pill">{o.status}</span>
                  </div>
                  <div className="admin-sniper-meta">
                    <div>
                      {o.method.toUpperCase()} · ${o.amount_usd}
                      {o.currency ? ` (${o.currency})` : ""}
                    </div>
                    {o.tx_hash && (
                      <div>
                        TX: <span className="admin-mono">{o.tx_hash}</span>
                      </div>
                    )}
                    {o.note && <div>{o.note}</div>}
                    {o.created_at && <div>{fmtDate(o.created_at)}</div>}
                  </div>
                  {o.status !== "completed" && o.status !== "rejected" && (
                    <div className="admin-actions" style={{ marginTop: 12 }}>
                      <button
                        type="button"
                        className="btn btn-primary btn-sm"
                        disabled={busyKey === `act-${o.id}`}
                        onClick={() =>
                          void runAction(
                            `act-${o.id}`,
                            async () => activateAdminOrder(o.id),
                            `Order #${o.id} activated`,
                          )
                        }
                      >
                        Activate plan
                      </button>
                      <button
                        type="button"
                        className="btn btn-outline btn-sm"
                        disabled={busyKey === `rej-${o.id}`}
                        onClick={() =>
                          void runAction(
                            `rej-${o.id}`,
                            async () => rejectAdminOrder(o.id),
                            `Order #${o.id} rejected`,
                          )
                        }
                      >
                        Reject
                      </button>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </PanelShell>
      ) : (
        <PanelShell
          title="Audit logs"
          desc="Read-only. Nothing here can be edited or deleted."
          onBack={goHome}
          tools={refreshBtn}
        >
          <form className="admin-toolbar" onSubmit={onLogSearch}>
            <input
              className="admin-search"
              value={logSearchInput}
              onChange={(e) => setLogSearchInput(e.target.value)}
              placeholder="Search actor, target, detail…"
            />
            <select
              className="admin-search"
              style={{ maxWidth: 200 }}
              value={logActionFilter}
              onChange={(e) => {
                setLogOffset(0);
                setLogActionFilter(e.target.value);
              }}
            >
              <option value="">All actions</option>
              {Object.entries(ACTION_LABELS).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
            <button type="submit" className="btn btn-primary btn-sm">
              Search
            </button>
          </form>

          {loading && logs.length === 0 ? (
            <p className="auth-loading">Loading admin logs…</p>
          ) : logs.length === 0 ? (
            <p className="admin-empty">No admin actions logged yet.</p>
          ) : (
            <div className="admin-table-wrap">
              <table className="admin-table">
                <thead>
                  <tr>
                    <th>When</th>
                    <th>Admin</th>
                    <th>Action</th>
                    <th>Target</th>
                    <th>Detail</th>
                  </tr>
                </thead>
                <tbody>
                  {logs.map((log) => (
                    <tr key={log.id}>
                      <td className="admin-muted">{fmtDate(log.created_at)}</td>
                      <td>
                        <div className="admin-user-name">{log.actor_username}</div>
                      </td>
                      <td>
                        <span className="admin-log-action">{actionLabel(log.action)}</span>
                      </td>
                      <td>
                        {log.target_username ? (
                          log.target_user_id != null ? (
                            <button
                              type="button"
                              className="admin-user-link"
                              onClick={() => openUserProfile(log.target_user_id!)}
                            >
                              <div className="admin-user-name">{log.target_username}</div>
                            </button>
                          ) : (
                            <div className="admin-user-name">{log.target_username}</div>
                          )
                        ) : (
                          <span className="admin-muted">—</span>
                        )}
                      </td>
                      <td className="admin-muted">{log.detail || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <div className="admin-pager">
            <span>{logPageLabel}</span>
            <div style={{ display: "flex", gap: 8 }}>
              <button
                type="button"
                className="btn btn-outline btn-sm"
                disabled={logOffset <= 0}
                onClick={() => setLogOffset((v) => Math.max(0, v - logLimit))}
              >
                Prev
              </button>
              <button
                type="button"
                className="btn btn-outline btn-sm"
                disabled={logOffset + logLimit >= logTotal}
                onClick={() => setLogOffset((v) => v + logLimit)}
              >
                Next
              </button>
            </div>
          </div>
        </PanelShell>
      )}
    </div>
  );
}

function GrantButtons({
  user,
  busyKey,
  onGrant,
}: {
  user: AdminUser;
  busyKey: string | null;
  onGrant: (planId: GrantPlanId, durationDays?: number) => void;
}) {
  const [customDays, setCustomDays] = useState("14");
  if (user.is_admin) return null;
  const plans: { id: GrantPlanId; label: string }[] = [
    { id: "premium-1-week", label: "+7d" },
    { id: "premium-1-month", label: "+1mo" },
    { id: "premium-lifetime", label: "Life" },
  ];
  const days = Math.floor(Number(customDays));
  const customOk = Number.isFinite(days) && days >= 1 && days <= 36500;
  return (
    <>
      {plans.map((p) => (
        <button
          key={p.id}
          type="button"
          className="btn btn-primary btn-sm"
          disabled={!!busyKey}
          onClick={() => onGrant(p.id)}
        >
          {busyKey === `grant-${user.id}-${p.id}-default` ? "…" : p.label}
        </button>
      ))}
      <input
        className="admin-search admin-grant-days"
        type="number"
        min={1}
        max={36500}
        step={1}
        value={customDays}
        disabled={!!busyKey}
        aria-label={`Custom premium days for ${user.username}`}
        onChange={(e) => setCustomDays(e.target.value)}
        style={{ width: 72, minWidth: 72 }}
      />
      <button
        type="button"
        className="btn btn-primary btn-sm"
        disabled={!!busyKey || !customOk}
        onClick={() => onGrant("premium-custom", days)}
      >
        {busyKey === `grant-${user.id}-premium-custom-${days}` ? "…" : `+${days}d`}
      </button>
    </>
  );
}

function SniperCard({
  sniper,
  busy,
  onStop,
  onOpen,
}: {
  sniper: AdminLiveSniper;
  busy: boolean;
  onStop: () => void;
  onOpen?: () => void;
}) {
  const pct = Math.max(0, Math.min(100, Number(sniper.progress_pct || 0)));
  const bad = Boolean(sniper.orphan || sniper.unauthorized);
  return (
    <div className={`admin-sniper-card${bad ? " is-bad" : ""}`}>
      <div className="admin-sniper-top">
        <div>
          {onOpen ? (
            <button type="button" className="admin-user-link" onClick={onOpen}>
              <div className="admin-user-name">{sniper.username ?? "unknown"}</div>
            </button>
          ) : (
            <div className="admin-user-name">{sniper.username ?? "unknown"}</div>
          )}
          <div className="admin-muted">
            {sniper.platform} · {sniper.state}
            {sniper.vps_pool ? ` · ${sniper.vps_pool}` : ""}
            {sniper.orphan ? " · orphan" : ""}
            {!sniper.orphan && sniper.unauthorized ? " · no plan" : ""}
          </div>
        </div>
        <span className="ph-status-pill">{sniper.state}</span>
      </div>
      <div className="admin-progress">
        <span style={{ width: `${pct}%` }} />
      </div>
      <div className="admin-sniper-meta">
        <div>
          <strong>{sniper.checks_done ?? 0}</strong> / {sniper.total_names ?? "?"} checks ·{" "}
          <strong>{Number(sniper.checks_per_sec || 0).toFixed(1)}</strong>/s
        </div>
        <div>
          hits <strong>{sniper.available ?? 0}</strong> · occupied {sniper.occupied ?? 0} · RL{" "}
          {sniper.rate_limits ?? 0} · err {sniper.errors ?? 0}
        </div>
        <div>
          elapsed {fmtElapsed(sniper.elapsed_seconds)} · IP{" "}
          <span className="admin-mono">{sniper.last_ip || "—"}</span>
        </div>
        {(sniper.orphan || !sniper.username) && (
          <div>
            token{" "}
            <span className="admin-mono">
              {sniper.token_prefix || sniper.user_token.slice(0, 12)}
            </span>
          </div>
        )}
        {sniper.current_target && (
          <div>
            target <span className="admin-mono">{sniper.current_target}</span>
          </div>
        )}
      </div>
      <div className="admin-actions" style={{ marginTop: 12 }}>
        {onOpen && (
          <button type="button" className="btn btn-primary btn-sm" onClick={onOpen}>
            Profile
          </button>
        )}
        <button type="button" className="btn btn-outline btn-sm" disabled={busy} onClick={onStop}>
          {busy ? "Stopping…" : "Force stop"}
        </button>
      </div>
    </div>
  );
}

function CopyField({
  label,
  value,
  onCopy,
  mono = true,
}: {
  label: string;
  value: string;
  onCopy: (value: string, label: string) => void;
  mono?: boolean;
}) {
  const empty = !value;
  return (
    <div className="admin-detail-field">
      <div className="admin-detail-field-top">
        <span>{label}</span>
        <button
          type="button"
          className="btn btn-outline btn-sm"
          disabled={empty}
          onClick={() => onCopy(value, label)}
        >
          Copy
        </button>
      </div>
      <div className={mono ? "admin-mono admin-detail-value" : "admin-detail-value"}>
        {empty ? "—" : value}
      </div>
    </div>
  );
}

function UserProfilePage({
  detail,
  loading,
  busyKey,
  section,
  onSection,
  onBack,
  onRefresh,
  onCopy,
  onStopSniper,
  onGrant,
  onResetTrial,
  onExpire,
  onClearProxies,
  onDelete,
}: {
  detail: AdminUserDetail | null;
  loading: boolean;
  busyKey: string | null;
  section: ProfileSection;
  onSection: (s: ProfileSection) => void;
  onBack: () => void;
  onRefresh: () => void;
  onCopy: (value: string, label: string) => void;
  onStopSniper: (token: string, platform: string) => void;
  onGrant: (planId: GrantPlanId, durationDays?: number) => void;
  onResetTrial: () => void;
  onExpire: () => void;
  onClearProxies: () => void;
  onDelete: () => void;
}) {
  const u = detail?.user;
  const sections: { id: ProfileSection; label: string; count?: number }[] = [
    { id: "account", label: "Account" },
    { id: "network", label: "Network" },
    { id: "proxies", label: "Proxies", count: detail?.proxies.length },
    { id: "snipers", label: "Snipers", count: detail?.live_snipers.length },
    { id: "jobs", label: "Jobs", count: detail?.recent_jobs.length },
    { id: "hits", label: "Hits", count: detail?.recent_hits.length },
    { id: "payments", label: "Payments", count: detail?.orders.length },
    { id: "logs", label: "Logs", count: detail?.audit_logs.length },
  ];

  return (
    <div className="admin-profile">
      <div className="admin-profile-bar">
        <button type="button" className="btn btn-outline btn-sm" onClick={onBack}>
          ← Back
        </button>
        <div className="admin-profile-bar-title">
          {u ? (
            <>
              <span className="admin-user-name">{u.username}</span>
              <span className="admin-muted">#{u.id}</span>
              <span className={`admin-rank ${rankClass(u)}`}>{u.rank || "—"}</span>
            </>
          ) : (
            <span className="admin-muted">Loading profile…</span>
          )}
        </div>
        <button type="button" className="btn btn-outline btn-sm" onClick={onRefresh}>
          {loading ? "Refreshing…" : "Refresh"}
        </button>
      </div>

      {!detail && loading ? (
        <p className="auth-loading">Loading account…</p>
      ) : !detail || !u ? (
        <p className="admin-empty">Profile not found.</p>
      ) : (
        <div className="admin-profile-body">
          <div className="admin-subnav">
            {sections.map((s) => (
              <button
                key={s.id}
                type="button"
                className={`admin-subnav-btn${section === s.id ? " active" : ""}`}
                onClick={() => onSection(s.id)}
              >
                {s.label}
                {typeof s.count === "number" ? ` (${s.count})` : ""}
              </button>
            ))}
          </div>

          {section === "account" && (
            <section className="admin-profile-section">
              <h3>Account</h3>
              <CopyField label="Username" value={u.username} onCopy={onCopy} mono={false} />
              <CopyField label="Session token" value={u.token || ""} onCopy={onCopy} />
              <CopyField label="Token prefix" value={u.token_prefix || ""} onCopy={onCopy} />
              <div className="admin-detail-field">
                <div className="admin-detail-field-top">
                  <span>Plan / trial</span>
                </div>
                <div className="admin-detail-value">
                  <div>
                    Rank <strong>{u.rank || "—"}</strong>
                    {u.has_active_plan ? " · active plan" : " · no active plan"}
                    {u.is_admin ? " · admin" : ""}
                  </div>
                  <div className="admin-muted" style={{ marginTop: 6 }}>
                    Expires {fmtDate(u.plan_expires_at)} · created {fmtDate(u.created_at)}
                  </div>
                  {(u.is_trial || u.trial_exhausted) && (
                    <div className="admin-muted" style={{ marginTop: 6 }}>
                      Trial {u.trial_used_seconds}s / {u.trial_limit_seconds}s
                      {u.trial_remaining_seconds != null
                        ? ` · ${u.trial_remaining_seconds}s left`
                        : ""}
                      {u.trial_exhausted ? " · exhausted" : ""}
                    </div>
                  )}
                  <div className="admin-muted" style={{ marginTop: 6 }}>
                    Proxies:{" "}
                    {u.using_trial_proxies
                      ? `shared trial pool (${u.trial_proxy_count} line(s))`
                      : u.can_manage_proxies
                        ? `custom list (${u.proxy_count})`
                        : "none"}
                    {" · "}
                    Names {u.names_count} · Session {u.has_session ? "active" : "none"}
                  </div>
                </div>
              </div>
              <div className="admin-actions" style={{ marginTop: 12 }}>
                <GrantButtons user={u} busyKey={busyKey} onGrant={onGrant} />
                <button
                  type="button"
                  className="btn btn-outline btn-sm"
                  disabled={!!busyKey || u.is_admin}
                  onClick={onResetTrial}
                >
                  Reset trial
                </button>
                <button
                  type="button"
                  className="btn btn-outline btn-sm"
                  disabled={!!busyKey || u.is_admin}
                  onClick={onExpire}
                >
                  Expire
                </button>
                <button
                  type="button"
                  className="btn btn-danger btn-sm"
                  disabled={!!busyKey || u.is_admin}
                  onClick={onDelete}
                >
                  Delete
                </button>
              </div>
            </section>
          )}

          {section === "network" && (
            <section className="admin-profile-section">
              <h3>Network</h3>
              <CopyField label="Last IP" value={u.last_ip || ""} onCopy={onCopy} />
              <CopyField label="Registration IP" value={u.registration_ip || ""} onCopy={onCopy} />
              <CopyField
                label="Webhook URL"
                value={detail.settings.webhook_url || ""}
                onCopy={onCopy}
              />
              <div className="admin-detail-field">
                <div className="admin-detail-field-top">
                  <span>Webhook settings</span>
                </div>
                <div className="admin-detail-value admin-muted">
                  mode {detail.settings.webhook_mode || "—"} · bot{" "}
                  {detail.settings.webhook_bot_username || "—"}
                  {detail.settings.webhook_user_id
                    ? ` · ping ${detail.settings.webhook_user_id}`
                    : ""}
                  {detail.settings.webhook_embed_enabled ? " · embeds on" : ""}
                </div>
              </div>
              {detail.settings.webhook_message_template && (
                <CopyField
                  label="Webhook template"
                  value={detail.settings.webhook_message_template}
                  onCopy={onCopy}
                  mono={false}
                />
              )}
            </section>
          )}

          {section === "proxies" && (
            <section className="admin-profile-section">
              <div className="admin-profile-section-head">
                <h3>
                  Proxies{" "}
                  <span className="admin-muted">
                    (
                    {u.using_trial_proxies
                      ? "trial pool — not stored on account"
                      : detail.proxies.length}
                    )
                  </span>
                </h3>
                {detail.proxies.length > 0 && (
                  <div className="admin-proxy-actions">
                    <button
                      type="button"
                      className="btn btn-outline btn-sm"
                      onClick={() => onCopy(detail.proxies.join("\n"), "all proxies")}
                    >
                      Copy all
                    </button>
                    <button
                      type="button"
                      className="btn btn-danger btn-sm"
                      disabled={!!busyKey || u.using_trial_proxies}
                      onClick={onClearProxies}
                    >
                      {busyKey === `clear-proxies-${u.id}` ? "Clearing…" : "Clear proxies"}
                    </button>
                  </div>
                )}
              </div>
              {u.using_trial_proxies ? (
                <p className="admin-muted">
                  This account uses the shared trial proxy pool ({u.trial_proxy_count} line
                  {u.trial_proxy_count === 1 ? "" : "s"}). Custom proxies appear here after upgrade.
                </p>
              ) : detail.proxies.length === 0 ? (
                <p className="admin-empty">No custom proxies saved.</p>
              ) : (
                <div className="admin-proxy-list">
                  {detail.proxies.map((line) => (
                    <div key={line} className="admin-proxy-row">
                      <span className="admin-mono">{line}</span>
                      <button
                        type="button"
                        className="btn btn-outline btn-sm admin-proxy-copy"
                        onClick={() => onCopy(line, "proxy")}
                      >
                        Copy
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </section>
          )}

          {section === "snipers" && (
            <section className="admin-profile-section">
              <h3>Live snipers ({detail.live_snipers.length})</h3>
              {detail.live_snipers.length === 0 ? (
                <p className="admin-empty">Not sniping right now.</p>
              ) : (
                <div className="admin-sniper-grid">
                  {detail.live_snipers.map((s) => (
                    <SniperCard
                      key={`${s.user_token}-${s.platform}`}
                      sniper={s}
                      busy={busyKey === `stop-${s.user_token}-${s.platform}`}
                      onStop={() => onStopSniper(s.user_token, s.platform)}
                    />
                  ))}
                </div>
              )}
            </section>
          )}

          {section === "jobs" && (
            <section className="admin-profile-section">
              <h3>Recent jobs ({detail.recent_jobs.length})</h3>
              {detail.recent_jobs.length === 0 ? (
                <p className="admin-empty">No jobs yet.</p>
              ) : (
                <div className="admin-table-wrap">
                  <table className="admin-table admin-table-compact">
                    <thead>
                      <tr>
                        <th>Platform</th>
                        <th>Status</th>
                        <th>Workers</th>
                        <th>Targets</th>
                        <th>Created</th>
                      </tr>
                    </thead>
                    <tbody>
                      {detail.recent_jobs.map((j) => (
                        <tr key={j.id}>
                          <td>{j.platform}</td>
                          <td>{j.status}</td>
                          <td>{j.workers}</td>
                          <td>{j.targets_count ?? "—"}</td>
                          <td className="admin-muted">{fmtDate(j.created_at)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>
          )}

          {section === "hits" && (
            <section className="admin-profile-section">
              <h3>Captures / hits ({detail.recent_hits.length})</h3>
              {detail.recent_hits.length === 0 ? (
                <p className="admin-empty">No hits recorded.</p>
              ) : (
                <div className="admin-table-wrap">
                  <table className="admin-table admin-table-compact">
                    <thead>
                      <tr>
                        <th>Target</th>
                        <th>Platform</th>
                        <th>Status</th>
                        <th>When</th>
                      </tr>
                    </thead>
                    <tbody>
                      {detail.recent_hits.map((h) => (
                        <tr key={h.id}>
                          <td className="admin-mono">{h.target}</td>
                          <td>{h.platform}</td>
                          <td>{h.status}</td>
                          <td className="admin-muted">{fmtDate(h.created_at)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>
          )}

          {section === "payments" && (
            <section className="admin-profile-section">
              <h3>Payments ({detail.orders.length})</h3>
              {detail.orders.length === 0 ? (
                <p className="admin-empty">No payment orders.</p>
              ) : (
                <div className="admin-table-wrap">
                  <table className="admin-table admin-table-compact">
                    <thead>
                      <tr>
                        <th>Plan</th>
                        <th>Method</th>
                        <th>Status</th>
                        <th>Amount</th>
                        <th>When</th>
                      </tr>
                    </thead>
                    <tbody>
                      {detail.orders.map((o) => (
                        <tr key={o.id}>
                          <td>{o.plan_id}</td>
                          <td>{o.method}</td>
                          <td>{o.status}</td>
                          <td>${o.amount_usd ?? "—"}</td>
                          <td className="admin-muted">{fmtDate(o.created_at)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>
          )}

          {section === "logs" && (
            <section className="admin-profile-section">
              <h3>Admin actions ({detail.audit_logs.length})</h3>
              {detail.audit_logs.length === 0 ? (
                <p className="admin-empty">No admin actions logged yet.</p>
              ) : (
                <div className="admin-table-wrap">
                  <table className="admin-table admin-table-compact">
                    <thead>
                      <tr>
                        <th>When</th>
                        <th>Actor</th>
                        <th>Action</th>
                        <th>Detail</th>
                      </tr>
                    </thead>
                    <tbody>
                      {detail.audit_logs.map((log) => (
                        <tr key={log.id}>
                          <td className="admin-muted">{fmtDate(log.created_at)}</td>
                          <td>{log.actor_username}</td>
                          <td>
                            <span className="admin-log-action">{actionLabel(log.action)}</span>
                          </td>
                          <td className="admin-muted">{log.detail || "—"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>
          )}
        </div>
      )}
    </div>
  );
}
