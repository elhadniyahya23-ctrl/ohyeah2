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

export default function LoginPage() {
  const { login, user, loading: authLoading } = useAuth();
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
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

    setLoading(true);
    try {
      await login(username.trim(), password);
      router.push("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <PhantomAuthPage>
      <AuthShell
        mode="login"
        footer={
          <AuthFooterLink
            text="Don't have an account?"
            linkText="Create one"
            href="/signup"
          />
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

          <button type="submit" className="btn btn-primary auth-submit" disabled={loading}>
            {loading ? "LOGGING IN…" : "SIGN IN"}
          </button>
        </form>
      </AuthShell>
    </PhantomAuthPage>
  );
}
