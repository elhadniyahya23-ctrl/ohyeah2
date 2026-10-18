"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useAuth } from "@/context/AuthContext";
import { useAuthModal } from "@/context/AuthModalContext";
import { useToast } from "@/context/ToastContext";
import { NAME_GENERATORS } from "@/lib/nameGenerators";
import {
  PREVIEW_SUFFIX_RE,
  clearNames,
  fetchNames,
  generateNames,
  notifyNamesUpdated,
  pollNameJob,
  reverseNames,
  saveNames,
  shuffleNames,
  uploadNamesFile,
} from "@/lib/namesApi";
import { getGlobalNames, setGlobalNames } from "@/lib/globalStore";

export function NamesPanel() {
  const { user } = useAuth();
  const { openAuth } = useAuthModal();
  const { showToast } = useToast();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [text, setText] = useState("");
  const [count, setCount] = useState(0);
  const [stackCount, setStackCount] = useState(0);
  const [stackLimit, setStackLimit] = useState(10);
  const [isLarge, setIsLarge] = useState(false);
  // Default ON so 2C then 2L adds both lists (users expect stack, not replace).
  const [stackList, setStackList] = useState(true);
  const [infiniteList, setInfiniteList] = useState(false);
  const [busyType, setBusyType] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const applyPayload = useCallback(
    (content: string, total: number, large: boolean, stacks = 0, limit = 10) => {
      setText(content);
      setCount(total);
      setIsLarge(large);
      setStackCount(stacks);
      setStackLimit(limit);
      if (!large) {
        const names = content.split(/\r?\n/).filter((l) => l.trim() && !PREVIEW_SUFFIX_RE.test(l));
        setGlobalNames(names);
      } else {
        setGlobalNames([]);
      }
      notifyNamesUpdated(total);
    },
    [],
  );

  const load = useCallback(async () => {
    if (!user) {
      const names = getGlobalNames();
      applyPayload(names.join("\n"), names.length, false, 0, 10);
      return names.length;
    }
    setLoading(true);
    try {
      const data = await fetchNames();
      applyPayload(
        data.content,
        data.count,
        data.is_large,
        data.stack_count ?? 0,
        data.stack_limit ?? 10,
      );
      return data.count;
    } catch (err) {
      showToast(err instanceof Error ? err.message : "Failed to load names", "error");
      return 0;
    } finally {
      setLoading(false);
    }
  }, [user, applyPayload, showToast]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const storedInfinite = window.localStorage.getItem("phantom_infinite_list");
    // Default OFF — only enable when user explicitly set "1".
    setInfiniteList(storedInfinite === "1");
    const storedStack = window.localStorage.getItem("phantom_stack_list");
    // Default ON — only disable when user explicitly set "0".
    if (storedStack === "0") setStackList(false);
    else {
      setStackList(true);
      if (storedStack !== "1") window.localStorage.setItem("phantom_stack_list", "1");
    }
  }, []);

  const setStack = (on: boolean) => {
    setStackList(on);
    if (typeof window !== "undefined") {
      window.localStorage.setItem("phantom_stack_list", on ? "1" : "0");
    }
    showToast(
      on
        ? `Stack ON — next generators add to your list (max ${stackLimit}, e.g. 4C + 2C)`
        : "Stack OFF — next generator replaces the whole list",
      "info",
    );
  };

  const setInfinite = (on: boolean) => {
    setInfiniteList(on);
    if (typeof window !== "undefined") {
      window.localStorage.setItem("phantom_infinite_list", on ? "1" : "0");
    }
    showToast(
      on
        ? "Infinite list ON — sniper will loop forever until you stop"
        : "Infinite list OFF — sniper stops after one pass",
      "info",
    );
  };

  const requireAuth = () => {
    openAuth("signup", true);
    showToast("Log in to use name generators", "info");
    return false;
  };

  const handleGenerate = async (type: string) => {
    if (!user) return requireAuth();
    if (busyType) return;
    if (stackList && stackCount >= stackLimit) {
      showToast(
        `Stack limit reached (${stackLimit} lists). Clear the list or turn stack off.`,
        "warning",
      );
      return;
    }
    setBusyType(type);
    try {
      // Capture toggle at click time — avoid stale state if effect races.
      const append =
        typeof window !== "undefined"
          ? window.localStorage.getItem("phantom_stack_list") !== "0"
          : stackList;
      let result = await generateNames(type, append);
      if (result.async && result.job_id) {
        result = await pollNameJob(result.job_id);
      }
      notifyNamesUpdated(result.count);
      const depth = result.stack_count ?? (append ? stackCount + 1 : 1);
      setStackCount(depth);
      const added = typeof result.added === "number" ? result.added : null;
      showToast(
        append
          ? `Stacked ${type}${added != null ? `: +${added.toLocaleString()}` : ""} → ${result.count.toLocaleString()} total (${depth}/${stackLimit})`
          : `Replaced list with ${type} → ${result.count.toLocaleString()} names`,
        "success",
      );
      await load();
    } catch (err) {
      showToast(err instanceof Error ? err.message : "Generation failed", "error");
    } finally {
      setBusyType(null);
    }
  };

  const handleSave = async () => {
    if (isLarge) {
      showToast("Large lists cannot be edited here — import a file to replace the list", "warning");
      return;
    }
    if (!user) {
      const names = text.split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
      if (names.length === 0) {
        showToast("No names to save", "warning");
        return;
      }
      setGlobalNames(names);
      setCount(names.length);
      notifyNamesUpdated(names.length);
      showToast(`Saved ${names.length} name${names.length === 1 ? "" : "s"} locally`, "success");
      return;
    }
    try {
      const result = await saveNames(text, stackList);
      if (result.count === 0) {
        showToast("No names to save", "warning");
        return;
      }
      showToast(`Saved ${result.count.toLocaleString()} name${result.count === 1 ? "" : "s"}`, "success");
      await load();
    } catch (err) {
      showToast(err instanceof Error ? err.message : "Save failed", "error");
    }
  };

  const handleClear = async () => {
    if (!user) {
      setText("");
      setCount(0);
      setGlobalNames([]);
      notifyNamesUpdated(0);
      showToast("Name list cleared", "info");
      return;
    }
    try {
      await clearNames();
      showToast("Name list cleared", "info");
      await load();
    } catch (err) {
      showToast(err instanceof Error ? err.message : "Clear failed", "error");
    }
  };

  const handleImport = () => fileInputRef.current?.click();

  const onFilePicked = async (file: File) => {
    if (!user) return requireAuth();
    try {
      const result = await uploadNamesFile(file, stackList);
      showToast(
        stackList
          ? `Stacked import → ${result.count.toLocaleString()} names total`
          : `Imported ${result.count.toLocaleString()} names`,
        "success",
      );
      await load();
    } catch (err) {
      showToast(err instanceof Error ? err.message : "Import failed", "error");
    }
  };

  return (
    <>
      <div className="tab-header">
        <div>
          <h2 className="tab-title">Username List</h2>
          <p className="tab-desc-sm">
            Add usernames to check, one per line. Checked top to bottom.
          </p>
        </div>
        <div className="count-pill glass-card" id="name-count-pill">
          <span>{count.toLocaleString()}</span> names
        </div>
      </div>

      <div className="glass-card textarea-card">
        <textarea
          id="names-textarea"
          className="code-textarea"
          placeholder={"# Add one username per line\nshadow\nmidnight\nzenith\nnova"}
          spellCheck={false}
          value={text}
          readOnly={isLarge || loading}
          onChange={(e) => setText(e.target.value)}
          onBlur={() => {
            if (!isLarge && !user && text.trim()) handleSave();
          }}
        />
      </div>

      <div style={{ marginTop: 10 }}>
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            marginBottom: 8,
            flexWrap: "wrap",
            gap: 8,
          }}
        >
          <p style={{ fontSize: 12, color: "var(--text-muted)", margin: 0 }}>
            List Generation &amp; Import
          </p>
          <div style={{ display: "flex", gap: 15, alignItems: "center", flexWrap: "wrap" }}>
            <label
              style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer", marginRight: 10 }}
              title="When ON, each generator adds to the list (max 10). Newest batch shows at the top. When OFF, each generator replaces the list."
            >
              <div className="toggle-switch" style={{ transform: "scale(0.85)", transformOrigin: "left" }}>
                <input
                  type="checkbox"
                  id="chk-append-names"
                  checked={stackList}
                  onChange={(e) => setStack(e.target.checked)}
                />
                <span className="toggle-slider" />
              </div>
              <span style={{ fontSize: 12, fontWeight: 600, color: "var(--accent)", textTransform: "lowercase" }}>
                stack list
                {stackList && stackCount > 0 ? ` (${stackCount}/${stackLimit})` : ""}
              </span>
            </label>
            <button
              type="button"
              className={`btn btn-sm ${infiniteList ? "btn-primary" : "btn-outline"}`}
              title="Sniper loop only — does not stack generators. Use stack list to add 2C + 2L together."
              onClick={() => setInfinite(!infiniteList)}
              style={
                infiniteList
                  ? {
                      background: "linear-gradient(135deg, #f59e0b, #ef4444)",
                      border: "none",
                      color: "#fff",
                      fontWeight: 800,
                    }
                  : undefined
              }
            >
              {infiniteList ? "∞ Infinite ON" : "∞ Infinite list"}
            </button>
            <button type="button" className="btn btn-outline btn-sm" onClick={handleClear}>
              Clear list
            </button>
            <button
              type="button"
              className="btn btn-outline btn-sm"
              title="Shuffle all names"
              onClick={async () => {
                if (!user) return requireAuth();
                try {
                  const result = await shuffleNames();
                  showToast(`Randomized ${result.count.toLocaleString()} names`, "success");
                  await load();
                } catch (err) {
                  showToast(err instanceof Error ? err.message : "Shuffle failed", "error");
                }
              }}
            >
              Randomize
            </button>
            <button
              type="button"
              className="btn btn-outline btn-sm"
              title="Reverse order (bottom → top)"
              onClick={async () => {
                if (!user) return requireAuth();
                try {
                  const result = await reverseNames();
                  showToast(`Reversed ${result.count.toLocaleString()} names`, "success");
                  await load();
                } catch (err) {
                  showToast(err instanceof Error ? err.message : "Reverse failed", "error");
                }
              }}
            >
              Reverse ↑↓
            </button>
          </div>
        </div>

        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          {NAME_GENERATORS.map((gen) => (
            <button
              key={gen.type}
              type="button"
              className={`btn btn-sm btn-generate${gen.outline ? " btn-outline" : ""}`}
              data-type={gen.type}
              style={gen.style}
              disabled={!!busyType}
              onClick={() => handleGenerate(gen.type)}
            >
              {busyType === gen.type ? "…" : gen.label}
            </button>
          ))}
        </div>
      </div>

      <div className="btn-row" style={{ marginTop: 20 }}>
        <button type="button" className="btn btn-outline" onClick={handleImport}>
          Import File
        </button>
        {!isLarge && (
          <button type="button" className="btn btn-primary btn-glow" onClick={handleSave}>
            Save Names
          </button>
        )}
      </div>

      <input
        ref={fileInputRef}
        type="file"
        accept=".txt,.csv"
        hidden
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) onFilePicked(file);
          e.target.value = "";
        }}
      />
    </>
  );
}
