import type { PlatformId } from "@/lib/platforms";

export type AppView =
  | "dashboard"
  | "sniper"
  | "names"
  | "proxies"
  | "results"
  | "settings"
  | "shop"
  | "admin";

export interface PlatformNavMeta {
  slug: string;
  sectionLabel: string;
  sectionClass: string;
  iconId: string;
  sniperClass: string;
  dashTab: string;
  sniperTab: string;
  dashLabel: string;
  sniperLabel: string;
}

export const PLATFORM_NAV: Record<PlatformId, PlatformNavMeta> = {
  discord: {
    slug: "discord",
    sectionLabel: "DISCORD",
    sectionClass: "nav-section-discord",
    iconId: "nav-icon-discord",
    sniperClass: "sniper-discord",
    dashTab: "dashboard",
    sniperTab: "sniper",
    dashLabel: "Discord Dash",
    sniperLabel: "Discord Sniper",
  },
  roblox: {
    slug: "roblox",
    sectionLabel: "ROBLOX",
    sectionClass: "nav-section-roblox",
    iconId: "nav-icon-roblox",
    sniperClass: "sniper-roblox",
    dashTab: "roblox-dashboard",
    sniperTab: "roblox-sniper",
    dashLabel: "Roblox Dash",
    sniperLabel: "Roblox Sniper",
  },
  minecraft: {
    slug: "mc",
    sectionLabel: "MINECRAFT",
    sectionClass: "nav-section-mc",
    iconId: "nav-icon-minecraft",
    sniperClass: "sniper-mc",
    dashTab: "mc-dashboard",
    sniperTab: "mc-sniper",
    dashLabel: "MC Dashboard",
    sniperLabel: "MC Sniper",
  },
  telegram: {
    slug: "tg",
    sectionLabel: "TELEGRAM",
    sectionClass: "nav-section-tg",
    iconId: "nav-icon-telegram",
    sniperClass: "sniper-tg",
    dashTab: "tg-dashboard",
    sniperTab: "tg-sniper",
    dashLabel: "TG Dashboard",
    sniperLabel: "TG Sniper",
  },
  whatsapp: {
    slug: "wa",
    sectionLabel: "WHATSAPP",
    sectionClass: "nav-section-wa",
    iconId: "nav-icon-whatsapp",
    sniperClass: "sniper-wa",
    dashTab: "wa-dashboard",
    sniperTab: "wa-sniper",
    dashLabel: "WA Dash",
    sniperLabel: "WA Sniper",
  },
  instagram: {
    slug: "ig",
    sectionLabel: "INSTAGRAM",
    sectionClass: "nav-section-ig",
    iconId: "nav-icon-instagram",
    sniperClass: "sniper-ig",
    dashTab: "ig-dashboard",
    sniperTab: "ig-sniper",
    dashLabel: "IG Dashboard",
    sniperLabel: "IG Sniper",
  },
  tiktok: {
    slug: "tt",
    sectionLabel: "TIKTOK",
    sectionClass: "nav-section-tt",
    iconId: "nav-icon-tiktok",
    sniperClass: "sniper-tt",
    dashTab: "tt-dashboard",
    sniperTab: "tt-sniper",
    dashLabel: "TikTok Dash",
    sniperLabel: "TikTok Sniper",
  },
  twitter: {
    slug: "x",
    sectionLabel: "X / TWITTER",
    sectionClass: "nav-section-x",
    iconId: "nav-icon-x",
    sniperClass: "sniper-x",
    dashTab: "x-dashboard",
    sniperTab: "x-sniper",
    dashLabel: "X Dash",
    sniperLabel: "X Sniper",
  },
  github: {
    slug: "gh",
    sectionLabel: "GITHUB",
    sectionClass: "nav-section-gh",
    iconId: "nav-icon-github",
    sniperClass: "sniper-gh",
    dashTab: "gh-dashboard",
    sniperTab: "gh-sniper",
    dashLabel: "GitHub Dash",
    sniperLabel: "GitHub Sniper",
  },
  snapchat: {
    slug: "snap",
    sectionLabel: "SNAPCHAT",
    sectionClass: "nav-section-snap",
    iconId: "nav-icon-snapchat",
    sniperClass: "sniper-snap",
    dashTab: "snap-dashboard",
    sniperTab: "snap-sniper",
    dashLabel: "Snap Dash",
    sniperLabel: "Snap Sniper",
  },
  steam: {
    slug: "steam",
    sectionLabel: "STEAM",
    sectionClass: "nav-section-steam",
    iconId: "nav-icon-steam",
    sniperClass: "sniper-steam",
    dashTab: "steam-dashboard",
    sniperTab: "steam-sniper",
    dashLabel: "Steam Dash",
    sniperLabel: "Steam Sniper",
  },
  reddit: {
    slug: "rd",
    sectionLabel: "REDDIT",
    sectionClass: "nav-section-rd",
    iconId: "nav-icon-reddit",
    sniperClass: "sniper-rd",
    dashTab: "rd-dashboard",
    sniperTab: "rd-sniper",
    dashLabel: "Reddit Dash",
    sniperLabel: "Reddit Sniper",
  },
  youtube: {
    slug: "yt",
    sectionLabel: "YOUTUBE",
    sectionClass: "nav-section-yt",
    iconId: "nav-icon-youtube",
    sniperClass: "sniper-yt",
    dashTab: "yt-dashboard",
    sniperTab: "yt-sniper",
    dashLabel: "YouTube Dash",
    sniperLabel: "YouTube Sniper",
  },
  guns: {
    slug: "guns",
    sectionLabel: "GUNS.LOL",
    sectionClass: "nav-section-guns",
    iconId: "nav-icon-guns",
    sniperClass: "sniper-guns",
    dashTab: "guns-dashboard",
    sniperTab: "guns-sniper",
    dashLabel: "Guns.lol Dash",
    sniperLabel: "Guns.lol Sniper",
  },
  epic: {
    slug: "ep",
    sectionLabel: "EPIC GAMES",
    sectionClass: "nav-section-ep",
    iconId: "nav-icon-epic",
    sniperClass: "sniper-ep",
    dashTab: "ep-dashboard",
    sniperTab: "ep-sniper",
    dashLabel: "Epic Dash",
    sniperLabel: "Epic Sniper",
  },
  ubisoft: {
    slug: "ubi",
    sectionLabel: "UBISOFT",
    sectionClass: "nav-section-ubi",
    iconId: "nav-icon-ubisoft",
    sniperClass: "sniper-ubi",
    dashTab: "ubi-dashboard",
    sniperTab: "ubi-sniper",
    dashLabel: "Ubisoft Dash",
    sniperLabel: "Ubisoft Sniper",
  },
};

export function navTabForView(platform: PlatformId, view: AppView): string {
  if (view === "names") return "names";
  if (view === "proxies") return "proxies";
  if (view === "results") return "results";
  if (view === "settings") return "settings";
  if (view === "shop") return "shop";
  if (view === "admin") return "admin";
  const meta = PLATFORM_NAV[platform];
  if (view === "dashboard") return meta.dashTab;
  return meta.sniperTab;
}
