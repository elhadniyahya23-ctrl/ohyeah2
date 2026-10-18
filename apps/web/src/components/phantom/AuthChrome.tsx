"use client";

import { useEffect } from "react";
import { useAuth } from "@/context/AuthContext";
import { useAuthModal } from "@/context/AuthModalContext";

interface Props {
  onMenuToggle?: () => void;
}

export function AuthChrome({ onMenuToggle }: Props) {
  const { user, loading } = useAuth();
  const { openAuth } = useAuthModal();
  const showUser = Boolean(user);

  useEffect(() => {
    document.body.classList.toggle("user-logged-in", showUser);
    return () => document.body.classList.remove("user-logged-in");
  }, [showUser]);

  return (
    <div className="mobile-top-bar">
      <header className="mobile-header">
        <button
          type="button"
          className="sidebar-toggle"
          aria-label="Open menu"
          onClick={onMenuToggle}
        >
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <line x1="3" y1="12" x2="21" y2="12" />
            <line x1="3" y1="6" x2="21" y2="6" />
            <line x1="3" y1="18" x2="21" y2="18" />
          </svg>
        </button>
        <div className="brand-name">PHANTOM</div>
      </header>

      <div className="auth-buttons-container">
        {showUser ? (
          <button
            type="button"
            id="btn-top-right-auth"
            className="create-account-btn"
            title="Account"
            onClick={() => openAuth("profile", true)}
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
              <circle cx="12" cy="7" r="4" />
            </svg>
            <span id="btn-top-right-auth-text">{user!.username}</span>
          </button>
        ) : loading ? (
          <div className="create-account-btn create-account-btn--ghost" style={{ opacity: 0.6, pointerEvents: "none" }}>
            <span>…</span>
          </div>
        ) : (
          <>
            <button
              type="button"
              id="btn-top-right-login"
              className="create-account-btn create-account-btn--ghost"
              title="Log In"
              onClick={() => openAuth("login", true)}
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4" />
                <polyline points="10 17 15 12 10 7" />
                <line x1="15" y1="12" x2="3" y2="12" />
              </svg>
              <span>Log In</span>
            </button>
            <button
              type="button"
              id="btn-top-right-signup"
              className="create-account-btn"
              title="Sign Up"
              onClick={() => openAuth("signup", true)}
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
                <circle cx="12" cy="7" r="4" />
              </svg>
              <span id="btn-top-right-signup-text">Sign Up</span>
            </button>
          </>
        )}
      </div>
    </div>
  );
}
