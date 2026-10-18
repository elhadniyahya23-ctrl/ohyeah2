const NAMES_KEY = "phantom_global_names";
const PROXIES_KEY = "phantom_global_proxies";

function readJson<T>(key: string, fallback: T): T {
  if (typeof window === "undefined") return fallback;
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return fallback;
    return JSON.parse(raw) as T;
  } catch {
    return fallback;
  }
}

function writeJson(key: string, value: unknown): void {
  if (typeof window === "undefined") return;
  localStorage.setItem(key, JSON.stringify(value));
}

export function getGlobalNames(): string[] {
  return readJson<string[]>(NAMES_KEY, []);
}

export function setGlobalNames(names: string[]): void {
  writeJson(NAMES_KEY, names);
}

export function getGlobalProxies(): string[] {
  return readJson<string[]>(PROXIES_KEY, []);
}

export function setGlobalProxies(proxies: string[]): void {
  writeJson(PROXIES_KEY, proxies);
}

export function parseLines(text: string): string[] {
  const out: string[] = [];
  for (const chunk of text.split(/[\r\n,;]+/)) {
    const trimmed = chunk.trim();
    if (!trimmed || trimmed.startsWith("#")) continue;

    // Multi-provider paste on one line: "flash… dataimpulse… adam…"
    const spaced = trimmed.split(/\s+/).filter(Boolean);
    const proxyish = spaced.filter((t) => {
      if (t.includes("://") || t.includes("@")) return true;
      const parts = t.split(":");
      return parts.length >= 4 && /^\d{2,5}$/.test(parts[1] ?? "");
    });
    if (spaced.length > 1 && proxyish.length >= 2) {
      out.push(...proxyish);
      continue;
    }
    out.push(trimmed);
  }
  return out;
}
