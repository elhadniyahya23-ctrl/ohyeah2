"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import {
  AuthSessionError,
  clearSession,
  fetchCurrentUser,
  getStoredSession,
  getStoredToken,
  loginUser,
  logoutUser,
  registerUser,
  saveSession,
  type AuthUser,
} from "@/lib/auth";
import { notifyNamesUpdated } from "@/lib/namesApi";
import { syncGuestNamesToServer } from "@/lib/syncGuestNames";

interface AuthContextValue {
  user: AuthUser | null;
  loading: boolean;
  login: (username: string, password: string) => Promise<void>;
  register: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
  applyUserPatch: (patch: Partial<AuthUser>) => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(() => getStoredSession());
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    const token = getStoredToken();

    if (!token) {
      setUser(null);
      return;
    }

    try {
      const me = await fetchCurrentUser(token);
      setUser(me);
      saveSession(me);
    } catch (err) {
      if (err instanceof AuthSessionError && err.unauthorized) {
        clearSession();
        setUser(null);
        return;
      }
      const cached = getStoredSession();
      if (cached) {
        setUser(cached);
      }
    }
  }, []);

  const applyUserPatch = useCallback((patch: Partial<AuthUser>) => {
    setUser((prev) => {
      if (!prev) return prev;
      const changed = (Object.keys(patch) as (keyof AuthUser)[]).some(
        (key) => patch[key] !== undefined && prev[key] !== patch[key],
      );
      if (!changed) return prev;
      const next = { ...prev, ...patch };
      saveSession(next);
      return next;
    });
  }, []);

  useEffect(() => {
    const token = getStoredToken();
    if (!token) {
      setUser(null);
      setLoading(false);
      return;
    }

    const cached = getStoredSession();
    if (cached) {
      setUser(cached);
    }
    setLoading(false);

    void refresh();
  }, [refresh]);

  // Keep trial balance in sync without logout — server resets / billing updates apply live.
  useEffect(() => {
    const token = getStoredToken();
    if (!token) return;
    const id = window.setInterval(() => {
      void refresh();
    }, 20_000);
    return () => window.clearInterval(id);
  }, [refresh, user?.token]);

  useEffect(() => {
    const onVisible = () => {
      if (document.visibilityState === "visible" && getStoredToken()) {
        void refresh();
      }
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => document.removeEventListener("visibilitychange", onVisible);
  }, [refresh]);

  const login = useCallback(async (username: string, password: string) => {
    const result = await loginUser(username, password);
    saveSession(result);
    setUser(result);
    const sync = await syncGuestNamesToServer();
    if (sync.uploaded > 0) notifyNamesUpdated(sync.uploaded);
  }, []);

  const register = useCallback(async (username: string, password: string) => {
    const result = await registerUser(username, password);
    saveSession(result);
    setUser(result);
    const sync = await syncGuestNamesToServer();
    if (sync.uploaded > 0) notifyNamesUpdated(sync.uploaded);
  }, []);

  const logout = useCallback(async () => {
    const token = getStoredToken();
    if (token) {
      try {
        await logoutUser(token);
      } catch {
        /* ignore */
      }
    }
    clearSession();
    setUser(null);
  }, []);

  const value = useMemo(
    () => ({ user, loading, login, register, logout, refresh, applyUserPatch }),
    [user, loading, login, register, logout, refresh, applyUserPatch],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
