"use client";

import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";
import {
  AuthInputIcon,
  AuthShell,
} from "@/components/auth/AuthShell";
import { useAuth } from "@/context/AuthContext";
import { useAuthModal, type AuthModalView } from "@/context/AuthModalContext";
import { formatPlanLabel, validatePassword, validateUsername } from "@/lib/auth";

function UserIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
      <circle cx="12" cy="7" r="4" />
    </svg>
  );
}

function LockIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
      <path d="M7 11V7a5 5 0 0 1 10 0v4" />
    </svg>
  );
}

function PlanIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z" />
    </svg>
  );
}

function CalendarIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <rect x="3" y="4" width="18" height="18" rx="2" ry="2" />
      <line x1="16" y1="2" x2="16" y2="6" />
      <line x1="8" y1="2" x2="8" y2="6" />
      <line x1="3" y1="10" x2="21" y2="10" />
    </svg>
  );
}

function LogoutIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
      <polyline points="16 17 21 12 16 7" />
      <line x1="21" y1="12" x2="9" y2="12" />
    </svg>
  );
}

function getInitials(username: string): string {
  const trimmed = username.trim();
  if (!trimmed) return "?";
  const parts = trimmed.split(/[_\s-]+/).filter(Boolean);
  if (parts.length >= 2) {
    return (parts[0][0] + parts[1][0]).toUpperCase();
  }
  return trimmed.slice(0, 2).toUpperCase();
}

export function AuthModal() {
  const router = useRouter();
  const { user, login, register, logout } = useAuth();
  const { view, overlay, closeAuth, setView } = useAuthModal();

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (overlay && view) {
      document.body.classList.add("modal-open");
    } else {
      document.body.classList.remove("modal-open");
    }
    return () => document.body.classList.remove("modal-open");
  }, [overlay, view]);

  if (!overlay || !view) return null;

  const resetFields = () => {
    setUsername("");
    setPassword("");
    setConfirm("");
    setError(null);
  };

  const close = () => {
    resetFields();
    closeAuth();
  };

  const switchView = (next: AuthModalView) => {
    setError(null);
    setView(next);
  };

  const handleLogin = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    const userErr = validateUsername(username);
    if (userErr) return setError(userErr);
    const passErr = validatePassword(password);
    if (passErr) return setError(passErr);

    setSubmitting(true);
    try {
      await login(username.trim(), password);
      resetFields();
      closeAuth();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setSubmitting(false);
    }
  };

  const handleSignup = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    const userErr = validateUsername(username);
    if (userErr) return setError(userErr);
    const passErr = validatePassword(password);
    if (passErr) return setError(passErr);
    if (password !== confirm) return setError("Passwords do not match");

    setSubmitting(true);
    try {
      await register(username.trim(), password);
      resetFields();
      closeAuth();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sign up failed");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      id="auth-modal"
      className="modal-wrapper open"
      onClick={(e) => {
        if (e.target === e.currentTarget) close();
      }}
    >
      {view === "profile" && user ? (
          <AuthShell
            mode="account"
            onClose={close}
            footer={
              <button
                type="button"
                className="btn auth-logout-btn"
                onClick={async () => {
                  await logout();
                  close();
                  router.push("/");
                }}
              >
                <LogoutIcon />
                Log out
              </button>
            }
          >
            <div className="auth-profile">
              <div className="auth-profile-hero">
                <div className="auth-profile-avatar" aria-hidden="true">
                  <span className="auth-profile-initials">{getInitials(user.username)}</span>
                </div>
                <h2 className="auth-profile-name">{user.username}</h2>
                <span
                  className={`auth-profile-status${user.has_active_plan ? " auth-profile-status--active" : ""}`}
                >
                  <span className="auth-profile-status-dot" aria-hidden="true" />
                  {user.has_active_plan ? "Active plan" : "No active plan"}
                </span>
              </div>

              <div className="auth-profile-stats">
                <div className="auth-profile-stat">
                  <div className="auth-profile-stat-icon" aria-hidden="true">
                    <PlanIcon />
                  </div>
                  <div className="auth-profile-stat-body">
                    <span className="auth-profile-stat-label">Plan</span>
                    <span className={`auth-plan-badge${user.has_active_plan ? " active" : ""}`}>
                      {formatPlanLabel(user)}
                    </span>
                  </div>
                </div>
                {user.plan_expires_at && (
                  <div className="auth-profile-stat">
                    <div className="auth-profile-stat-icon" aria-hidden="true">
                      <CalendarIcon />
                    </div>
                    <div className="auth-profile-stat-body">
                      <span className="auth-profile-stat-label">Expires</span>
                      <span className="auth-profile-value">
                        {new Date(user.plan_expires_at).toLocaleDateString(undefined, {
                          year: "numeric",
                          month: "short",
                          day: "numeric",
                        })}
                      </span>
                    </div>
                  </div>
                )}
              </div>
            </div>
          </AuthShell>
        ) : view === "login" || (view === "profile" && !user) ? (
          <AuthShell
            mode="login"
            onClose={close}
            footer={
              <p className="auth-form-footer">
                Don&apos;t have an account?{" "}
                <button type="button" onClick={() => switchView("signup")}>
                  Create one
                </button>
              </p>
            }
          >
            <form className="auth-form" onSubmit={handleLogin}>
              {error && <div className="auth-form-error">{error}</div>}
              <label className="auth-field">
                <AuthInputIcon>
                  <UserIcon />
                </AuthInputIcon>
                <input
                  className="input-field"
                  type="text"
                  autoComplete="username"
                  placeholder="Username"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  required
                />
              </label>
              <label className="auth-field auth-field--password">
                <AuthInputIcon>
                  <LockIcon />
                </AuthInputIcon>
                <input
                  className="input-field"
                  type="password"
                  autoComplete="current-password"
                  placeholder="Password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                />
              </label>
              <button
                type="submit"
                className="btn btn-primary auth-submit"
                disabled={submitting}
              >
                {submitting ? "LOGGING IN…" : "SIGN IN"}
              </button>
            </form>
          </AuthShell>
        ) : (
          <AuthShell
            mode="signup"
            onClose={close}
            footer={
              <>
                <p className="auth-form-footer">
                  Already have an account?{" "}
                  <button type="button" onClick={() => switchView("login")}>
                    Sign in
                  </button>
                </p>
                <p className="auth-legal">
                  Secure connection ·{" "}
                  <a href="/terms.html" target="_blank" rel="noopener noreferrer">
                    Terms
                  </a>{" "}
                  ·{" "}
                  <a href="/privacy.html" target="_blank" rel="noopener noreferrer">
                    Privacy
                  </a>{" "}
                  · <a href="mailto:support@usersniper.com">support@usersniper.com</a>
                </p>
              </>
            }
          >
            <form className="auth-form" onSubmit={handleSignup}>
              {error && <div className="auth-form-error">{error}</div>}
              <label className="auth-field">
                <AuthInputIcon>
                  <UserIcon />
                </AuthInputIcon>
                <input
                  className="input-field"
                  type="text"
                  autoComplete="username"
                  placeholder="Choose Username"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  required
                />
              </label>
              <label className="auth-field">
                <AuthInputIcon>
                  <LockIcon />
                </AuthInputIcon>
                <input
                  className="input-field"
                  type="password"
                  autoComplete="new-password"
                  placeholder="Create Password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                />
              </label>
              <label className="auth-field">
                <AuthInputIcon>
                  <LockIcon />
                </AuthInputIcon>
                <input
                  className="input-field"
                  type="password"
                  autoComplete="new-password"
                  placeholder="Confirm Password"
                  value={confirm}
                  onChange={(e) => setConfirm(e.target.value)}
                  required
                />
              </label>
              <button
                type="submit"
                className="btn btn-primary auth-submit auth-submit--signup"
                disabled={submitting}
              >
                {submitting ? "CREATING…" : "CREATE ACCOUNT"}
              </button>
            </form>
          </AuthShell>
        )}
    </div>
  );
}
