"use client";

import { useEffect, useRef, useState } from "react";
import { AmbientBackground } from "@/components/phantom/AmbientBackground";
import { AuthChrome } from "@/components/phantom/AuthChrome";
import { DiscordBadge } from "@/components/phantom/DiscordBadge";
import { NavIconSprite } from "@/components/phantom/NavIcons";
import { AuthModal } from "@/components/auth/AuthModal";
import { Sidebar } from "@/components/layout/Sidebar";
import { AdminPanel } from "@/components/panels/AdminPanel";
import { DashboardPanel } from "@/components/panels/DashboardPanel";
import { NamesPanel } from "@/components/panels/NamesPanel";
import { ProxiesPanel } from "@/components/panels/ProxiesPanel";
import { ResultsPanel } from "@/components/panels/ResultsPanel";
import { SettingsPanel } from "@/components/panels/SettingsPanel";
import { ShopPanel } from "@/components/panels/ShopPanel";
import { SniperPanel } from "@/components/panels/SniperPanel";
import { useAuth } from "@/context/AuthContext";
import { useAuthModal } from "@/context/AuthModalContext";
import { useSniperUiState } from "@/hooks/useSniperUiState";
import { useToast } from "@/context/ToastContext";
import { canManageProxies } from "@/lib/auth";
import { PLATFORMS, type PlatformId } from "@/lib/platforms";
import { PLATFORM_NAV, type AppView } from "@/lib/platformNav";

export function App() {
  const { showToast } = useToast();
  const { user, refresh, applyUserPatch } = useAuth();
  const { openAuth } = useAuthModal();
  const [platform, setPlatform] = useState<PlatformId>("discord");
  const [view, setView] = useState<AppView>("dashboard");
  const [filter, setFilter] = useState("");
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [trialBanner, setTrialBanner] = useState(false);
  const redirectedRef = useRef(false);

  const active = PLATFORMS.find((p) => p.id === platform)!;
  const navMeta = PLATFORM_NAV[platform];
  const { status, statuses, clearCaptures, requestStart, requestStop } =
    useSniperUiState(platform);

  useEffect(() => {
    if (view === "admin" && user && !user.is_admin) {
      setView("dashboard");
    }
  }, [view, user]);

  useEffect(() => {
    if (view === "proxies" && !canManageProxies(user)) {
      setView(user ? "shop" : "dashboard");
      if (!user) openAuth("signup", true);
    }
  }, [view, user, openAuth]);

  useEffect(() => {
    const goShop = () => setView("shop");
    window.addEventListener("phantom-go-shop", goShop);
    return () => window.removeEventListener("phantom-go-shop", goShop);
  }, []);

  useEffect(() => {
    if (!user?.is_trial) return;
    const patch: Partial<NonNullable<typeof user>> = {};
    if (typeof status.trial_remaining_seconds === "number") {
      patch.trial_remaining_seconds = status.trial_remaining_seconds;
      const limit = user.trial_limit_seconds ?? 300;
      patch.trial_used_seconds = Math.max(0, limit - status.trial_remaining_seconds);
      patch.trial_exhausted = status.trial_remaining_seconds <= 0;
      patch.has_active_plan = status.trial_remaining_seconds > 0;
      if (status.trial_remaining_seconds > 0) {
        patch.rank = "Free Trial";
      }
    }
    if (typeof status.trial_exhausted === "boolean") {
      patch.trial_exhausted = status.trial_exhausted;
    }
    if (Object.keys(patch).length > 0) {
      applyUserPatch(patch);
    }
  }, [
    user?.is_trial,
    user?.trial_limit_seconds,
    status.trial_remaining_seconds,
    status.trial_exhausted,
    applyUserPatch,
  ]);

  useEffect(() => {
    const remaining = user?.trial_remaining_seconds;
    if (user?.is_trial && typeof remaining === "number" && remaining > 0 && !user.trial_exhausted) {
      redirectedRef.current = false;
      setTrialBanner(false);
    }
  }, [user?.is_trial, user?.trial_remaining_seconds, user?.trial_exhausted]);

  useEffect(() => {
    if (!user?.trial_exhausted) return;
    setTrialBanner(true);
    if (!redirectedRef.current) {
      redirectedRef.current = true;
      setView("shop");
    }
  }, [user?.trial_exhausted]);

  useEffect(() => {
    if (!status.redirect_to_payment && !status.trial_exhausted) {
      return;
    }
    if (redirectedRef.current) return;
    redirectedRef.current = true;
    setTrialBanner(true);
    setView("shop");
    void refresh();
    showToast("Free trial ended — upgrade to keep sniping", "info");
  }, [status.redirect_to_payment, status.trial_exhausted, refresh, showToast]);

  const handleStart = async (names: string[], proxies: string[], infinite = false) => {
    try {
      await requestStart(names, proxies, infinite);
      setView("dashboard");
      showToast(
        infinite
          ? `${active.label} sniper started (infinite loop)`
          : `${active.label} sniper started`,
        "success",
      );
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to start sniper";
      if (/trial|upgrade|shop|plan has expired/i.test(msg)) {
        setTrialBanner(true);
        setView("shop");
      }
      showToast(msg, "error");
      throw err;
    }
  };

  const handleStop = async () => {
    await requestStop();
    showToast(`${active.label} sniper stopped`, "info");
  };

  return (
    <>
      <NavIconSprite />
      <AmbientBackground />
      <DiscordBadge />
      <AuthChrome onMenuToggle={() => setSidebarOpen((o) => !o)} />

      <div
        className={`sidebar-overlay${sidebarOpen ? " active" : ""}`}
        onClick={() => setSidebarOpen(false)}
        aria-hidden={!sidebarOpen}
      />

      <div className="screen active" id="screen-app">
        <div className="app-layout">
          <Sidebar
            platform={platform}
            view={view}
            filter={filter}
            sidebarOpen={sidebarOpen}
            onPlatform={setPlatform}
            onView={setView}
            onFilter={setFilter}
            onCloseSidebar={() => setSidebarOpen(false)}
          />

          <main className="content">
            <div className={view === "names" ? "tab active" : "tab"} id="tab-names">
              {view === "names" && <NamesPanel />}
            </div>

            <div className={view === "proxies" ? "tab active" : "tab"} id="tab-proxies">
              {view === "proxies" && <ProxiesPanel />}
            </div>

            <div className={view === "results" ? "tab active" : "tab"} id="tab-results">
              {view === "results" && (
                <ResultsPanel statuses={statuses} onCleared={clearCaptures} />
              )}
            </div>

            <div className={view === "settings" ? "tab active" : "tab"} id="tab-settings">
              {view === "settings" && <SettingsPanel />}
            </div>

            <div className={view === "shop" ? "tab active" : "tab"} id="tab-shop">
              {view === "shop" && <ShopPanel trialBanner={trialBanner} />}
            </div>

            <div className={view === "admin" ? "tab active" : "tab"} id="tab-admin">
              {view === "admin" && <AdminPanel />}
            </div>

            <div
              className={`tab sniper-panel ${navMeta.sniperClass}${view === "dashboard" ? " active" : ""}`}
              id={`tab-${navMeta.dashTab}`}
            >
              {view === "dashboard" && (
                <DashboardPanel
                  platform={platform}
                  platformLabel={active.label}
                  status={status}
                />
              )}
            </div>

            <div
              className={`tab sniper-panel ${navMeta.sniperClass}${view === "sniper" ? " active" : ""}`}
              id={`tab-${navMeta.sniperTab}`}
            >
              {view === "sniper" && (
                <SniperPanel
                  platform={platform}
                  platformLabel={active.label}
                  status={status}
                  onStart={handleStart}
                  onStop={handleStop}
                  onGoNames={() => setView("names")}
                  onGoProxies={() => setView("proxies")}
                />
              )}
            </div>
          </main>
        </div>
      </div>
      <AuthModal />
    </>
  );
}
