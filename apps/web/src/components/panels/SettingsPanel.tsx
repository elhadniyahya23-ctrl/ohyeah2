"use client";

import { useCallback, useEffect, useState } from "react";
import { useAuth } from "@/context/AuthContext";
import { useAuthModal } from "@/context/AuthModalContext";
import { useToast } from "@/context/ToastContext";
import {
  fetchSettings,
  saveSettings,
  testWebhook,
  type UserSettings,
  type WebhookMode,
} from "@/lib/settingsApi";

const DEFAULT_SETTINGS: UserSettings = {
  webhook_url: "",
  webhook_mode: "none",
  webhook_user_id: "",
  webhook_message_template: "{platform} username available: `{username}`",
  webhook_bot_username: "User Sniper",
  webhook_avatar_url: "",
  webhook_embed_enabled: false,
  webhook_embed_title: "",
  webhook_embed_description: "",
  webhook_embed_color: "#5865F2",
  webhook_embed_footer: "",
  webhook_embed_footer_icon: "",
  webhook_embed_thumbnail: false,
  webhook_embed_thumbnail_url: "",
  webhook_embed_author_name: "",
  webhook_embed_author_icon: "",
};

export function SettingsPanel() {
  const { user } = useAuth();
  const { openAuth } = useAuthModal();
  const { showToast } = useToast();
  const [settings, setSettings] = useState<UserSettings>(DEFAULT_SETTINGS);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);

  const load = useCallback(async () => {
    if (!user) {
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      const data = await fetchSettings();
      setSettings({ ...DEFAULT_SETTINGS, ...data });
    } catch (err) {
      showToast(err instanceof Error ? err.message : "Failed to load settings", "error");
    } finally {
      setLoading(false);
    }
  }, [user, showToast]);

  useEffect(() => {
    load();
  }, [load]);

  const update = <K extends keyof UserSettings>(key: K, value: UserSettings[K]) => {
    setSettings((prev) => ({ ...prev, [key]: value }));
  };

  const setMode = (mode: WebhookMode) => update("webhook_mode", mode);

  const handleSave = async () => {
    if (!user) {
      openAuth("signup", true);
      return;
    }
    setSaving(true);
    try {
      await saveSettings(settings);
      showToast("Settings saved", "success");
    } catch (err) {
      showToast(err instanceof Error ? err.message : "Save failed", "error");
    } finally {
      setSaving(false);
    }
  };

  const handleTest = async () => {
    if (!settings.webhook_url.trim()) {
      showToast("Add a Discord webhook URL first", "warning");
      return;
    }
    setTesting(true);
    try {
      await testWebhook({
        url: settings.webhook_url,
        webhook_mode: settings.webhook_mode,
        webhook_user_id: settings.webhook_user_id,
        webhook_message_template: settings.webhook_message_template,
        webhook_bot_username: settings.webhook_bot_username,
        webhook_avatar_url: settings.webhook_avatar_url,
        webhook_embed_enabled: settings.webhook_embed_enabled,
      });
      showToast("Test webhook sent", "success");
    } catch (err) {
      showToast(err instanceof Error ? err.message : "Webhook test failed", "error");
    } finally {
      setTesting(false);
    }
  };

  const copyBrace = async (char: string) => {
    try {
      await navigator.clipboard.writeText(char);
      showToast(`Copied ${char}`, "info");
    } catch {
      showToast("Could not copy", "error");
    }
  };

  if (loading) {
    return <p className="auth-loading">Loading settings…</p>;
  }

  return (
    <>
      <div className="tab-header">
        <h2 className="tab-title">Settings</h2>
      </div>

      <div className="settings-stack">
        <div className="glass-card settings-section settings-webhook-core">
          <h3 className="settings-title">WEBHOOK CONFIG</h3>

          <div className="setting-row">
            <label htmlFor="setting-webhook-url">Discord Webhook URL</label>
            <div className="webhook-url-row">
              <input
                id="setting-webhook-url"
                type="text"
                className="input-field mono"
                placeholder="https://discord.com/api/webhooks/..."
                value={settings.webhook_url}
                onChange={(e) => update("webhook_url", e.target.value)}
              />
              <button
                type="button"
                className="btn btn-outline btn-sm"
                onClick={handleTest}
                disabled={testing}
              >
                {testing ? "…" : "Test"}
              </button>
            </div>
          </div>

          <div className="setting-row">
            <label>Ping Mode</label>
            <div className="webhook-ping-row">
              <div className="webhook-mode-toggle">
                <button
                  type="button"
                  className={`mode-btn${settings.webhook_mode === "everyone" ? " active" : ""}`}
                  onClick={() => setMode("everyone")}
                >
                  @everyone
                </button>
                <button
                  type="button"
                  className={`mode-btn${settings.webhook_mode === "user" ? " active" : ""}`}
                  onClick={() => setMode("user")}
                >
                  @User ID
                </button>
                <button
                  type="button"
                  className={`mode-btn${settings.webhook_mode === "none" ? " active" : ""}`}
                  onClick={() => setMode("none")}
                >
                  No ping
                </button>
              </div>
            </div>
          </div>

          {settings.webhook_mode === "user" && (
            <div className="setting-row">
              <label htmlFor="setting-webhook-userid">Discord User ID</label>
              <input
                id="setting-webhook-userid"
                type="text"
                className="input-field mono"
                placeholder="Ex: 123456789012345678"
                value={settings.webhook_user_id}
                onChange={(e) => update("webhook_user_id", e.target.value)}
              />
              <p className="webhook-hint">Right-click a Discord profile → Copy ID</p>
            </div>
          )}

          <div className="webhook-aesthetics-divider" />
          <h4 className="webhook-subtitle">Message &amp; appearance</h4>
          <p className="webhook-hint">
            Placeholders: <code>{"{username}"}</code>, <code>{"{platform}"}</code>,{" "}
            <code>{"{platform_lower}"}</code>, <code>{"{ping}"}</code>. Use <code>{"{{"}</code> and{" "}
            <code>{"}}"}</code> for literal braces.
            <span className="webhook-brace-copy" aria-label="Copy brace characters">
              <button type="button" className="webhook-brace-btn" onClick={() => copyBrace("{")}>
                {"{"}
              </button>
              <button type="button" className="webhook-brace-btn" onClick={() => copyBrace("}")}>
                {"}"}
              </button>
            </span>
          </p>

          <div className="setting-row">
            <label htmlFor="setting-webhook-message-template">Hit message template</label>
            <input
              id="setting-webhook-message-template"
              type="text"
              className="input-field mono"
              placeholder="{platform} username available: `{username}`"
              value={settings.webhook_message_template}
              onChange={(e) => update("webhook_message_template", e.target.value)}
            />
          </div>

          <div className="settings-grid webhook-aesthetics-grid">
            <div className="setting-row">
              <label htmlFor="setting-webhook-bot-username">Webhook display name</label>
              <input
                id="setting-webhook-bot-username"
                type="text"
                className="input-field"
                placeholder="User Sniper"
                value={settings.webhook_bot_username}
                onChange={(e) => update("webhook_bot_username", e.target.value)}
              />
            </div>
            <div className="setting-row">
              <label htmlFor="setting-webhook-avatar-url">Webhook avatar URL</label>
              <input
                id="setting-webhook-avatar-url"
                type="text"
                className="input-field mono"
                placeholder="https://..."
                value={settings.webhook_avatar_url}
                onChange={(e) => update("webhook_avatar_url", e.target.value)}
              />
            </div>
          </div>

          <div className="setting-row webhook-embed-toggle-row">
            <label className="toggle-switch">
              <input
                type="checkbox"
                checked={settings.webhook_embed_enabled}
                onChange={(e) => update("webhook_embed_enabled", e.target.checked)}
              />
              <span className="toggle-slider" />
            </label>
            <span className="webhook-embed-toggle-label">Send rich embed (Discord card)</span>
          </div>
        </div>
      </div>

      <button
        type="button"
        id="btn-save-settings"
        className="btn btn-primary btn-glow"
        onClick={handleSave}
        disabled={saving}
        style={{ marginTop: 20 }}
      >
        {saving ? "SAVING…" : "Save Settings"}
      </button>
    </>
  );
}
