"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useAuth } from "@/context/AuthContext";
import { useAuthModal } from "@/context/AuthModalContext";
import { useToast } from "@/context/ToastContext";
import { canManageProxies } from "@/lib/auth";
import { getGlobalProxies, parseLines, setGlobalProxies } from "@/lib/globalStore";
import { fetchProxies, saveProxies } from "@/lib/proxiesApi";

function linesEqual(a: string[], b: string[]): boolean {
  if (a.length !== b.length) return false;
  for (let i = 0; i < a.length; i++) {
    if (a[i] !== b[i]) return false;
  }
  return true;
}

export function ProxiesPanel() {
  const { user } = useAuth();
  const { openAuth } = useAuthModal();
  const { showToast } = useToast();
  const toastRef = useRef(showToast);

  const [text, setText] = useState("");
  const [count, setCount] = useState(0);
  const [saving, setSaving] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const allowed = canManageProxies(user);

  useEffect(() => {
    toastRef.current = showToast;
  }, [showToast]);

  const load = useCallback(async () => {
    if (!allowed) return;
    if (user) {
      try {
        const data = await fetchProxies();
        setGlobalProxies(data.proxies);
        setText(data.proxies.join("\n"));
        setCount(data.count);
        setLoaded(true);
        return;
      } catch (err) {
        toastRef.current(
          err instanceof Error ? err.message : "Failed to load proxies from server",
          "error",
        );
      }
    }
    const proxies = getGlobalProxies();
    setText(proxies.join("\n"));
    setCount(proxies.length);
    setLoaded(true);
  }, [user, allowed]);

  useEffect(() => {
    void load();
  }, [load]);

  if (!user) {
    return (
      <>
        <div className="tab-header">
          <h2 className="tab-title">Proxy Manager</h2>
        </div>
        <div className="glass-card" style={{ padding: 24 }}>
          <p style={{ margin: "0 0 14px", color: "var(--text-muted)" }}>
            Create an account to unlock your own proxies after upgrading.
          </p>
          <button type="button" className="btn btn-primary" onClick={() => openAuth("signup", true)}>
            Sign up
          </button>
        </div>
      </>
    );
  }

  if (!allowed) {
    return (
      <>
        <div className="tab-header">
          <h2 className="tab-title">Proxy Manager</h2>
        </div>
        <div className="glass-card" style={{ padding: 24 }}>
          <p style={{ margin: "0 0 14px", color: "var(--text-muted)" }}>
            Free Trial uses our shared proxies. After you upgrade, this tab unlocks so you can paste
            your own proxy list.
          </p>
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => {
              window.dispatchEvent(new CustomEvent("phantom-go-shop"));
            }}
          >
            Go to Shop
          </button>
        </div>
      </>
    );
  }

  const save = async (raw: string, { silent = false }: { silent?: boolean } = {}) => {
    if (saving) return;
    const proxies = parseLines(raw);
    setSaving(true);
    setGlobalProxies(proxies);
    setCount(proxies.length);
    try {
      const result = await saveProxies(proxies);
      const confirmed = await fetchProxies().catch(() => null);
      if (confirmed) {
        setGlobalProxies(confirmed.proxies);
        // Avoid rewriting the textarea (causes visible jump/shake) when unchanged.
        if (!linesEqual(parseLines(text), confirmed.proxies)) {
          setText(confirmed.proxies.join("\n"));
        }
        setCount(confirmed.count);
      } else {
        setCount(result.count);
      }
      if (!silent) {
        const n = confirmed?.count ?? result.count;
        const bad = Number(result.invalid || 0);
        if (n === 0) {
          showToast("No valid proxies saved — check host:port:user:pass format", "warning");
        } else if (bad > 0) {
          showToast(
            `Saved ${n} prox${n === 1 ? "y" : "ies"} (${bad} invalid skipped)`,
            "success",
          );
        } else {
          showToast(`Saved ${n} prox${n === 1 ? "y" : "ies"}`, "success");
        }
      }
    } catch (err) {
      showToast(err instanceof Error ? err.message : "Failed to save proxies to server", "error");
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <div className="tab-header">
        <div>
          <h2 className="tab-title">Proxy Manager</h2>
          <p className="tab-desc-sm">
            One proxy per line — mix providers freely (FlashProxy, DataImpulse, …). Formats:{" "}
            <code>host:port:user:pass</code>, <code>user:pass@host:port</code>
          </p>
        </div>
        <div className="count-pill glass-card">
          <span>{count}</span> proxies
        </div>
      </div>

      <div className="glass-card textarea-card">
        <textarea
          className="code-textarea"
          placeholder={
            "# Mix providers — one line each\nlite.flashproxy.io:6969:user:pass\nuser:pass@gw.dataimpulse.com:823\nlite.proxyserver.bot:6969:user:pass"
          }
          spellCheck={false}
          value={text}
          disabled={!loaded}
          onChange={(e) => setText(e.target.value)}
        />
      </div>

      <div className="panel-actions">
        <button
          type="button"
          className="btn btn-outline"
          disabled={saving || !loaded}
          onClick={() => {
            setText("");
            void save("", { silent: false });
          }}
        >
          Clear
        </button>
        <button
          type="button"
          className="btn btn-primary proxies-save-btn"
          disabled={saving || !loaded}
          onClick={() => void save(text)}
        >
          {saving ? "Saving…" : "Save Proxies"}
        </button>
      </div>
    </>
  );
}
