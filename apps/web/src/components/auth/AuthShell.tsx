"use client";

import Link from "next/link";
import type { ReactNode } from "react";

interface Props {
  mode: "login" | "signup" | "account";
  children: ReactNode;
  footer?: ReactNode;
  onClose?: () => void;
}

export function AuthShell({ mode, children, footer, onClose }: Props) {
  const subtitle =
    mode === "signup"
      ? "Create your usersniper.com account"
      : mode === "account"
        ? "Your account overview"
        : "Official login for usersniper.com";

  return (
    <div className="login-wrapper">
      <div className={`modal-content auth-modal-card${mode === "account" ? " auth-modal-card--profile" : ""}`}>
        {onClose && (
          <button type="button" className="close-modal" onClick={onClose} aria-label="Close">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        )}
        {mode !== "account" && (
          <div className="auth-card-brand">
            <div className="login-logo" aria-hidden="true">
              <span className="logo-glow" />
              <span className="login-logo-text">PH</span>
            </div>
            <h2 className="login-title">PHANTOM</h2>
            <p className="login-subtitle">{subtitle}</p>
          </div>
        )}

        {mode === "account" ? (
          <p className="auth-profile-card-label">Account</p>
        ) : (
          <p className="auth-form-title">{mode === "login" ? "Sign In" : "Create Account"}</p>
        )}

        {children}
        {footer}
      </div>
    </div>
  );
}

export function AuthFooterLink({
  text,
  linkText,
  href,
}: {
  text: string;
  linkText: string;
  href: string;
}) {
  return (
    <p className="auth-form-footer">
      {text}{" "}
      <Link href={href}>{linkText}</Link>
    </p>
  );
}

export function AuthInputIcon({ children }: { children: ReactNode }) {
  return <span className="auth-input-icon">{children}</span>;
}
