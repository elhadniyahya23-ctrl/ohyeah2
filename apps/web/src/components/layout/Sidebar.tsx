"use client";

import { PLATFORMS, type PlatformId } from "@/lib/platforms";
import { PLATFORM_NAV, navTabForView, type AppView } from "@/lib/platformNav";
import { NavIcon } from "@/components/phantom/NavIcons";
import { useAuth } from "@/context/AuthContext";
import { useAuthModal } from "@/context/AuthModalContext";
import { canManageProxies } from "@/lib/auth";

export type { AppView };

const GLOBAL_NAV: { tab: string; label: string; icon: string }[] = [
  { tab: "names", label: "Names", icon: "nav-icon-names" },
  { tab: "proxies", label: "Proxies", icon: "nav-icon-proxies" },
  { tab: "results", label: "Results", icon: "nav-icon-results" },
];

interface Props {
  platform: PlatformId;
  view: AppView;
  filter: string;
  sidebarOpen: boolean;
  onPlatform: (id: PlatformId) => void;
  onView: (view: AppView) => void;
  onFilter: (q: string) => void;
  onCloseSidebar: () => void;
}

function navClass(tab: string, activeTab: string) {
  return `nav-item${tab === activeTab ? " active" : ""}`;
}

export function Sidebar({
  platform,
  view,
  filter,
  sidebarOpen,
  onPlatform,
  onView,
  onFilter,
  onCloseSidebar,
}: Props) {
  const { user } = useAuth();
  const { openAuth } = useAuthModal();
  const isAdmin = Boolean(user?.is_admin);
  const showProxies = canManageProxies(user);
  const activeTab = navTabForView(platform, view);
  const q = filter.trim().toLowerCase();

  const filtered = PLATFORMS.filter((p) => {
    if (!q) return true;
    const meta = PLATFORM_NAV[p.id];
    return (
      p.label.toLowerCase().includes(q) ||
      p.id.includes(q) ||
      meta.sectionLabel.toLowerCase().includes(q)
    );
  });

  const pickGlobal = (nextView: AppView) => {
    if (
      !user &&
      (nextView === "names" ||
        nextView === "results" ||
        nextView === "settings" ||
        nextView === "shop")
    ) {
      openAuth("signup", true);
      onCloseSidebar();
      return;
    }
    if (nextView === "proxies" && !canManageProxies(user)) {
      if (!user) openAuth("signup", true);
      else onView("shop");
      onCloseSidebar();
      return;
    }
    onView(nextView);
    onCloseSidebar();
  };

  const pickPlatform = (id: PlatformId, nextView: AppView) => {
    if (!user) {
      openAuth("signup", true);
      onCloseSidebar();
      return;
    }
    onPlatform(id);
    onView(nextView);
    onCloseSidebar();
  };

  const visibleGlobal = GLOBAL_NAV.filter((item) => item.tab !== "proxies" || showProxies);

  return (
    <nav className={`sidebar glass-card${sidebarOpen ? " active" : ""}`}>
      <div className="sidebar-brand" style={{ marginBottom: 20 }}>
        <span className="brand-name">PHANTOM</span>
      </div>

      <div className="sidebar-search" style={{ marginBottom: 20 }}>
        <input
          type="text"
          className="input-field"
          placeholder="Search platform..."
          value={filter}
          onChange={(e) => onFilter(e.target.value)}
          style={{
            width: "100%",
            padding: "8px 12px",
            fontSize: 13,
            background: "rgba(0, 0, 0, 0.2)",
            border: "1px solid var(--border-color)",
            borderRadius: 8,
            color: "var(--text-main)",
          }}
        />
      </div>

      <div className="nav-group">
        <div
          style={{
            margin: "0 16px 8px",
            fontSize: 10,
            color: "var(--text-muted)",
            letterSpacing: 2,
            textTransform: "uppercase",
          }}
        >
          GLOBAL
        </div>

        {visibleGlobal.map((item) => (
          <button
            key={item.tab}
            type="button"
            className={navClass(item.tab, activeTab)}
            data-tab={item.tab}
            onClick={() => pickGlobal(item.tab as AppView)}
          >
            <NavIcon id={item.icon} />
            <span className="nav-label">{item.label}</span>
          </button>
        ))}

        {filtered.map((p) => {
          const meta = PLATFORM_NAV[p.id];
          return (
            <div key={p.id}>
              <div className={`nav-section-label ${meta.sectionClass}`}>
                {meta.sectionLabel}
              </div>
              <button
                type="button"
                className={navClass(meta.dashTab, activeTab)}
                data-tab={meta.dashTab}
                onClick={() => pickPlatform(p.id, "dashboard")}
              >
                <NavIcon id={meta.iconId} />
                <span className="nav-label">{meta.dashLabel}</span>
              </button>
              <button
                type="button"
                className={navClass(meta.sniperTab, activeTab)}
                data-tab={meta.sniperTab}
                onClick={() => pickPlatform(p.id, "sniper")}
              >
                <NavIcon id="nav-icon-sniper" />
                <span className="nav-label">{meta.sniperLabel}</span>
              </button>
            </div>
          );
        })}

        <div
          style={{
            margin: "12px 16px 8px",
            fontSize: 10,
            color: "var(--text-muted)",
            letterSpacing: 2,
            textTransform: "uppercase",
            borderTop: "1px solid var(--border-color)",
            paddingTop: 12,
          }}
        >
          SETTINGS
        </div>
        <button
          type="button"
          className={navClass("shop", activeTab)}
          data-tab="shop"
          onClick={() => pickGlobal("shop")}
        >
          <NavIcon id="nav-icon-shop" />
          <span className="nav-label">Shop</span>
        </button>
        {isAdmin && (
          <button
            type="button"
            className={navClass("admin", activeTab)}
            data-tab="admin"
            onClick={() => pickGlobal("admin")}
          >
            <NavIcon id="nav-icon-admin" />
            <span className="nav-label">Admin</span>
          </button>
        )}
        <button
          type="button"
          className={navClass("settings", activeTab)}
          data-tab="settings"
          onClick={() => pickGlobal("settings")}
        >
          <NavIcon id="nav-icon-settings" />
          <span className="nav-label">Settings</span>
        </button>
      </div>

      <div className="sidebar-footer">
        <div className="footer-info">
          <span className="version-tag">PHANTOM SNIPER</span>
        </div>
      </div>
    </nav>
  );
}
