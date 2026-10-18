"use client";

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";

export type AuthModalView = "login" | "signup" | "profile";

interface AuthModalContextValue {
  view: AuthModalView | null;
  overlay: boolean;
  openAuth: (view: AuthModalView, overlay?: boolean) => void;
  closeAuth: () => void;
  setView: (view: AuthModalView) => void;
}

const AuthModalContext = createContext<AuthModalContextValue | null>(null);

export function AuthModalProvider({ children }: { children: ReactNode }) {
  const [view, setView] = useState<AuthModalView | null>(null);
  const [overlay, setOverlay] = useState(false);

  const openAuth = useCallback((next: AuthModalView, asOverlay = true) => {
    setView(next);
    setOverlay(asOverlay);
  }, []);

  const closeAuth = useCallback(() => {
    setView(null);
    setOverlay(false);
  }, []);

  const value = useMemo(
    () => ({ view, overlay, openAuth, closeAuth, setView }),
    [view, overlay, openAuth, closeAuth],
  );

  return (
    <AuthModalContext.Provider value={value}>{children}</AuthModalContext.Provider>
  );
}

export function useAuthModal() {
  const ctx = useContext(AuthModalContext);
  if (!ctx) throw new Error("useAuthModal must be used within AuthModalProvider");
  return ctx;
}
