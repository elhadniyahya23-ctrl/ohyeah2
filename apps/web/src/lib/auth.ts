import { getApiBase } from "@/lib/apiBase";

export interface AuthUser {
  user_id: number;
  username: string;
  token: string;
  rank: string | null;
  plan_expires_at: string | null;
  has_active_plan: boolean;
  is_admin?: boolean;
  is_trial?: boolean;
  can_manage_proxies?: boolean;
  trial_used_seconds?: number;
  trial_limit_seconds?: number;
  trial_remaining_seconds?: number | null;
  trial_exhausted?: boolean;
}

/** Paid users manage their own proxies; guests/trial use shared trial proxies. */
export function canManageProxies(user: AuthUser | null | undefined): boolean {
  if (!user) return false;
  if (user.can_manage_proxies != null) return Boolean(user.can_manage_proxies);
  if (user.is_admin) return true;
  return Boolean(user.has_active_plan && !user.is_trial);
}

const SESSION_KEY = "usersniper_session";
const LEGACY_TOKEN_KEY = "phantom_session_token";

export class AuthSessionError extends Error {
  readonly unauthorized: boolean;

  constructor(message: string, unauthorized: boolean) {
    super(message);
    this.name = "AuthSessionError";
    this.unauthorized = unauthorized;
  }
}

export function getStoredSession(): AuthUser | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = localStorage.getItem(SESSION_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as AuthUser;
    return parsed?.token ? parsed : null;
  } catch {
    return null;
  }
}

export function getStoredToken(): string | null {
  const session = getStoredSession();
  if (session?.token) return session.token;
  if (typeof window === "undefined") return null;
  const legacy = localStorage.getItem(LEGACY_TOKEN_KEY);
  if (legacy && legacy !== "default") return legacy;
  return null;
}

export function saveSession(user: AuthUser): void {
  if (typeof window === "undefined") return;
  localStorage.setItem(SESSION_KEY, JSON.stringify(user));
  localStorage.setItem(LEGACY_TOKEN_KEY, user.token);
}

export function clearSession(): void {
  if (typeof window === "undefined") return;
  localStorage.removeItem(SESSION_KEY);
  localStorage.removeItem(LEGACY_TOKEN_KEY);
  localStorage.removeItem("phantom_logged_in");
  localStorage.removeItem("phantom_username");
}

export function getAuthHeaders(): Record<string, string> {
  const token = getStoredToken();
  return token ? { "X-Session-Token": token } : {};
}

const REQUEST_TIMEOUT_MS = 15_000;

async function fetchWithTimeout(
  url: string,
  init: RequestInit,
  timeoutMs = REQUEST_TIMEOUT_MS,
): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, { ...init, signal: controller.signal });
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new Error("Server took too long to respond. Please try again.");
    }
    throw new Error("Cannot reach the API. Check your connection and try again.");
  } finally {
    clearTimeout(timer);
  }
}

async function parseError(res: Response): Promise<string> {
  try {
    const data = await res.json();
    if (typeof data.detail === "string") return data.detail;
    if (Array.isArray(data.detail)) return data.detail[0]?.msg ?? "Request failed";
  } catch {
    /* ignore */
  }
  if (res.status === 401) return "Invalid username or password";
  if (res.status === 409) return "Username already taken";
  return "Something went wrong. Please try again.";
}

export async function loginUser(username: string, password: string): Promise<AuthUser> {
  const res = await fetchWithTimeout(`${getApiBase()}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function registerUser(username: string, password: string): Promise<AuthUser> {
  const res = await fetchWithTimeout(`${getApiBase()}/api/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function fetchCurrentUser(token: string): Promise<AuthUser> {
  try {
    const res = await fetchWithTimeout(`${getApiBase()}/api/auth/me`, {
      headers: { "X-Session-Token": token },
      cache: "no-store",
    });
    if (res.status === 401) {
      throw new AuthSessionError("Session expired", true);
    }
    if (!res.ok) {
      throw new AuthSessionError("Could not verify session", false);
    }
    return res.json();
  } catch (err) {
    if (err instanceof AuthSessionError) throw err;
    throw new AuthSessionError(
      err instanceof Error ? err.message : "Could not verify session",
      false,
    );
  }
}

export async function logoutUser(token: string): Promise<void> {
  await fetchWithTimeout(`${getApiBase()}/api/auth/logout`, {
    method: "POST",
    headers: { "X-Session-Token": token },
  });
}

export function formatPlanLabel(user: AuthUser): string {
  if (user.has_active_plan && user.rank) return user.rank;
  if (user.plan_expires_at) {
    const exp = new Date(user.plan_expires_at);
    if (exp > new Date()) return user.rank ?? "Active plan";
  }
  return user.rank ?? "Free";
}

export function validateUsername(username: string): string | null {
  const trimmed = username.trim();
  if (trimmed.length < 3) return "Username must be at least 3 characters";
  if (trimmed.length > 32) return "Username must be 32 characters or less";
  if (!/^[a-zA-Z0-9_]+$/.test(trimmed)) {
    return "Use only letters, numbers, and underscores";
  }
  return null;
}

export function validatePassword(password: string): string | null {
  if (password.length < 6) return "Password must be at least 6 characters";
  if (password.length > 128) return "Password is too long";
  return null;
}
