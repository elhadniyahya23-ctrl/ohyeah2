"use client";

import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";
import { AuthFooterLink, AuthInputIcon, AuthShell } from "@/components/auth/AuthShell";
import { PhantomAuthPage } from "@/components/phantom/PhantomAuthPage";
import { useAuth } from "@/context/AuthContext";
import { validatePassword, validateUsername } from "@/lib/auth";

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

export default function SignupPage() {
  const { register, user, loading: authLoading } = useAuth();
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!authLoading && user) router.replace("/");
  }, [authLoading, user, router]);

  if (authLoading || user) {
    return (
      <PhantomAuthPage>
        <div className="login-wrapper">
          <p className="auth-loading">Loading…</p>
        </div>
      </PhantomAuthPage>
    );
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);

    const userErr = validateUsername(username);
    if (userErr) return setError(userErr);
    const passErr = validatePassword(password);
    if (passErr) return setError(passErr);
    if (password !== confirm) return setError("Passwords do not match");

    setLoading(true);
    try {
      await register(username.trim(), password);
      router.push("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sign up failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <PhantomAuthPage>
      <AuthShell
        mode="signup"
        footer={
          <>
            <AuthFooterLink
              text="Already have an account?"
              linkText="Sign in"
              href="/login"
            />
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
        <form className="auth-form" onSubmit={handleSubmit}>
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

          <button type="submit" className="btn btn-primary auth-submit auth-submit--signup" disabled={loading}>
            {loading ? "CREATING…" : "CREATE ACCOUNT"}
          </button>
        </form>
      </AuthShell>
    </PhantomAuthPage>
  );
}
