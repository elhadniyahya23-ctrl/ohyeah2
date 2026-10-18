import { parseApiError } from "@/lib/apiClient";
import { getApiBase } from "@/lib/apiBase";
import { getStoredToken } from "@/lib/auth";

export interface NamesPayload {
  content: string;
  is_large: boolean;
  count: number;
  stack_count?: number;
  stack_limit?: number;
}

function apiHeaders(): Record<string, string> {
  const token = getStoredToken();
  return token ? { "X-Session-Token": token } : {};
}

async function namesFetch(path: string, init?: RequestInit, timeoutMs = 45000) {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(`${getApiBase()}${path}`, {
      ...init,
      signal: controller.signal,
      headers: {
        ...(init?.headers ?? {}),
        ...apiHeaders(),
      },
    });
    if (res.status === 401) throw new Error("Please log in to manage names");
    if (!res.ok) {
      if (res.status === 413) {
        throw new Error("List too large (max 2 MB). Generate on the server or import a smaller file.");
      }
      if (res.status === 502 || res.status === 503 || res.status === 504) {
        throw new Error("API is temporarily unreachable — wait a few seconds and try again.");
      }
      await parseApiError(res, "Request failed");
    }
    return res.json();
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new Error("Server took too long — try a smaller list or wait and retry.");
    }
    if (err instanceof TypeError) {
      throw new Error("Cannot reach the API — check your connection and refresh.");
    }
    throw err;
  } finally {
    clearTimeout(timer);
  }
}

export async function fetchNames(): Promise<NamesPayload> {
  return namesFetch(`/api/names?_=${Date.now()}`, { cache: "no-store" });
}

export async function fetchNamesCount(): Promise<{ count: number; is_large: boolean }> {
  return namesFetch(`/api/names/count?_=${Date.now()}`, { cache: "no-store" }, 20000);
}

export async function saveNames(names: string, append: boolean): Promise<{ count: number }> {
  return namesFetch("/api/names", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ names, append }),
  });
}

export async function clearNames(): Promise<{ count: number }> {
  return saveNames("", false);
}

export async function shuffleNames(): Promise<{ count: number }> {
  return namesFetch("/api/names/shuffle", { method: "POST" });
}

export async function reverseNames(): Promise<{ count: number }> {
  return namesFetch("/api/names/reverse", { method: "POST" });
}

export async function generateNames(
  type: string,
  append: boolean,
  includeVerbs = true,
): Promise<{
  count: number;
  async?: boolean;
  job_id?: string;
  stack_count?: number;
  stack_limit?: number;
  added?: number;
  type?: string;
}> {
  return namesFetch("/api/names/generate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ type, append, include_verbs: includeVerbs }),
  }, 120000);
}

export async function pollNameJob(jobId: string): Promise<{ count: number }> {
  for (let i = 0; i < 120; i++) {
    const job = await namesFetch(`/api/names/job/${jobId}`, undefined, 15000);
    if (job.status === "done" && job.result) return job.result;
    if (job.status === "failed") throw new Error(job.error || "Name generation failed");
    await new Promise((r) => setTimeout(r, 1000));
  }
  throw new Error("Name generation timed out — try a smaller list.");
}

export async function uploadNamesFile(file: File, append = false): Promise<{ count: number }> {
  const form = new FormData();
  form.append("file", file);
  form.append("append", String(append));
  return namesFetch("/api/upload/names", { method: "POST", body: form });
}

export const NAMES_UPDATED_EVENT = "phantom-names-updated";

export function notifyNamesUpdated(count: number): void {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new CustomEvent(NAMES_UPDATED_EVENT, { detail: { count } }));
}

export const PREVIEW_SUFFIX_RE = /\n\.\.\. and \d+ more \(Preview limited to 1000\)$/;
