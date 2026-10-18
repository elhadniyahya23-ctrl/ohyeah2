import { apiFetch, parseApiError } from "@/lib/apiClient";

export type WebhookMode = "everyone" | "user" | "none";

export interface UserSettings {
  webhook_url: string;
  webhook_mode: WebhookMode;
  webhook_user_id: string;
  webhook_message_template: string;
  webhook_bot_username: string;
  webhook_avatar_url: string;
  webhook_embed_enabled: boolean;
  webhook_embed_title: string;
  webhook_embed_description: string;
  webhook_embed_color: string;
  webhook_embed_footer: string;
  webhook_embed_footer_icon: string;
  webhook_embed_thumbnail: boolean;
  webhook_embed_thumbnail_url: string;
  webhook_embed_author_name: string;
  webhook_embed_author_icon: string;
}

export async function fetchSettings(): Promise<UserSettings> {
  const res = await apiFetch("/api/settings");
  if (res.status === 401) throw new Error("Please log in to manage settings");
  if (!res.ok) await parseApiError(res, "Failed to load settings");
  return res.json();
}

export async function saveSettings(settings: Partial<UserSettings>): Promise<void> {
  const res = await apiFetch("/api/settings", {
    method: "POST",
    body: JSON.stringify(settings),
  });
  if (res.status === 401) throw new Error("Please log in to manage settings");
  if (!res.ok) await parseApiError(res, "Failed to save settings");
}

export async function testWebhook(payload: Partial<UserSettings> & { url: string; preview_platform?: string }): Promise<void> {
  const res = await apiFetch("/api/settings/test-webhook", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  if (res.status === 401) throw new Error("Please log in to test webhooks");
  if (!res.ok) await parseApiError(res, "Webhook test failed");
}
