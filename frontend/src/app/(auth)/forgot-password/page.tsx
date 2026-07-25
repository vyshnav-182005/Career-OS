"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";

import styles from "../auth.module.css";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sent, setSent] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setLoading(true);
    setError(null);

    const res = await fetch('/api/auth/forgot-password', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email })
    });
    const data = await res.json();

    if (!res.ok) {
      setError(data.error || 'Something went wrong.');
      setLoading(false);
      return;
    }

    setSent(true);
    setLoading(false);
  }

  return (
    <div className={styles.page}>
      <Link href="/login" className={styles.backLink}>Back to sign in</Link>
      <div className={styles.card}>
        <div className={styles.heading}>
          <h1 className={styles.title}>Reset your password</h1>
          <p className={styles.subtitle}>Enter your email and we&apos;ll send you a secure reset link.</p>
        </div>
        {sent ? (
          <div className={styles.successState}>
            <div className={styles.successIcon} aria-hidden="true">✓</div>
            <p className={styles.subtitle}>If an account exists for <strong>{email}</strong>, a reset link is on its way.</p>
            <Link href="/login" className="btn btn-primary">Return to sign in</Link>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className={styles.form}>
            {error && <div className={styles.errorAlert} role="alert">{error}</div>}
            <div className="form-group">
              <label htmlFor="reset-email" className="form-label">Email address</label>
              <input id="reset-email" type="email" className="form-input" placeholder="you@example.com" value={email} onChange={(event) => setEmail(event.target.value)} autoComplete="email" required disabled={loading} />
            </div>
            <button type="submit" className={`btn btn-primary ${styles.submitBtn}`} disabled={loading}>{loading ? "Sending link…" : "Send reset link"}</button>
          </form>
        )}
      </div>
    </div>
  );
}
