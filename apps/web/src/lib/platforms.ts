export const PLATFORMS = [
  { id: "discord", label: "Discord", color: "#5865F2" },
  { id: "roblox", label: "Roblox", color: "#E74C3C" },
  { id: "minecraft", label: "Minecraft", color: "#53B754" },
  { id: "telegram", label: "Telegram", color: "#29B6F6" },
  { id: "whatsapp", label: "WhatsApp", color: "#25D366" },
  { id: "instagram", label: "Instagram", color: "#E1306C" },
  { id: "tiktok", label: "TikTok", color: "#FE2C55" },
  { id: "twitter", label: "Twitter", color: "#1DA1F2" },
  { id: "github", label: "GitHub", color: "#8B949E" },
  { id: "snapchat", label: "Snapchat", color: "#FFFC00" },
  { id: "steam", label: "Steam", color: "#1B9AF3" },
  { id: "reddit", label: "Reddit", color: "#FF5700" },
  { id: "youtube", label: "YouTube", color: "#FF0000" },
  { id: "guns", label: "Guns.lol", color: "#FF5722" },
  { id: "epic", label: "Epic", color: "#FFFFFF" },
  { id: "ubisoft", label: "Ubisoft", color: "#0070FF" },
] as const;

/** Platforms with live turbo snipers (must match apps/api/sniper/registry.py). */
export const TURBO_PLATFORMS = [
  "discord",
  "roblox",
  "minecraft",
  "instagram",
  "tiktok",
  "guns",
] as const;

export const TURBO_PLATFORM_SET = new Set<string>(TURBO_PLATFORMS);

export const COMING_SOON_PLATFORMS = [
  "telegram",
  "whatsapp",
  "snapchat",
  "youtube",
  "epic",
  "twitter",
  "steam",
  "ubisoft",
  "github",
  "reddit",
] as const;

export type PlatformId = (typeof PLATFORMS)[number]["id"];
