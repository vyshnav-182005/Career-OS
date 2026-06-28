"use client";

export const dynamic = "force-dynamic";

import Link from "next/link";
import { useState, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { createClient } from "@/lib/supabase/client";
import styles from "../auth.module.css";

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const redirectTo = searchParams.get("redirectTo") || "/dashboard";

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const supabase = createClient();

  async function handleLogin(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);

    const { error } = await supabase.auth.signInWithPassword({ email, password });

    if (error) {
      setError(error.message);
      setLoading(false);
    } else {
      router.push(redirectTo);
      router.refresh();
    }
  }

  return (
    <div className={styles.card}>
      {/* Logo */}
      <div className={styles.logo}>
        <svg width="36" height="36" viewBox="0 0 36 36" fill="none" aria-hidden="true">
          <rect width="36" height="36" rx="10" fill="url(#login-logo-grad)" />
          <path d="M10 18L15 23L26 13" stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
          <defs>
            <linearGradient id="login-logo-grad" x1="0" y1="0" x2="36" y2="36" gradientUnits="userSpaceOnUse">
              <stop stopColor="#6366f1" />
              <stop offset="1" stopColor="#06b6d4" />
            </linearGradient>
          </defs>
        </svg>
        <span className={styles.logoText}>Career<span className="gradient-text">OS</span></span>
      </div>

      <div className={styles.heading}>
        <h1 className={styles.title}>Welcome back</h1>
        <p className={styles.subtitle}>Sign in to continue your career journey</p>
      </div>

      {error && (
        <div className={styles.errorAlert} role="alert">
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
            <circle cx="8" cy="8" r="7" stroke="#f87171" strokeWidth="1.5" />
            <path d="M8 5v4M8 11v.5" stroke="#f87171" strokeWidth="1.5" strokeLinecap="round" />
          </svg>
          {error}
        </div>
      )}

      <form onSubmit={handleLogin} className={styles.form} noValidate>
        <div className="form-group">
          <label htmlFor="login-email" className="form-label">Email address</label>
          <input
            id="login-email"
            type="email"
            className="form-input"
            placeholder="you@example.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            autoComplete="email"
            disabled={loading}
          />
        </div>

        <div className="form-group">
          <div className={styles.labelRow}>
            <label htmlFor="login-password" className="form-label">Password</label>
            <a href="#" className={styles.forgotLink}>Forgot password?</a>
          </div>
          <input
            id="login-password"
            type="password"
            className="form-input"
            placeholder="••••••••"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            autoComplete="current-password"
            disabled={loading}
          />
        </div>

        <button
          type="submit"
          id="login-submit"
          className={`btn btn-primary ${styles.submitBtn}`}
          disabled={loading}
        >
          {loading ? <span className="spinner" aria-hidden="true" /> : null}
          {loading ? "Signing in…" : "Sign in"}
        </button>
      </form>

      <p className={styles.switchLink}>
        Don&apos;t have an account?{" "}
        <Link href="/register">Create one</Link>
      </p>
    </div>
  );
}

export default function LoginPage() {
  return (
    <div className={styles.page}>
      {/* Background */}
      <div className={styles.orb1} aria-hidden="true" />
      <div className={styles.orb2} aria-hidden="true" />

      {/* Back to home */}
      <Link href="/" className={styles.backLink} aria-label="Back to home">
        <svg width="18" height="18" viewBox="0 0 18 18" fill="none" aria-hidden="true">
          <path d="M11.25 13.5L6.75 9l4.5-4.5" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
        Back to home
      </Link>

      <Suspense>
        <LoginForm />
      </Suspense>
    </div>
  );
}
