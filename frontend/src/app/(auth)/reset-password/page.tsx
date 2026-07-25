"use client";

import Link from "next/link";
import { FormEvent, useState, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import styles from "../auth.module.css";

function ResetPasswordForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const token = searchParams.get('token');
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    if (!token) return setError("Invalid reset link. Please request a new one.");
    if (password.length < 8) return setError("Password must be at least 8 characters.");
    if (password !== confirmPassword) return setError("Passwords do not match.");

    setLoading(true);
    const res = await fetch('/api/auth/reset-password', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token, password })
    });
    const data = await res.json();
    if (!res.ok) {
      setError(data.error || 'Something went wrong.');
      setLoading(false);
      return;
    }
    router.replace("/login");
    router.refresh();
  }

  if (!token) {
    return (
      <div className={styles.card}>
        <div className={styles.heading}>
          <h1 className={styles.title}>Invalid link</h1>
          <p className={styles.subtitle}>Invalid reset link. Please request a new one.</p>
        </div>
        <Link href="/forgot-password" className={`btn btn-primary ${styles.submitBtn}`}>Back to reset password</Link>
      </div>
    );
  }

  return (
    <div className={styles.card}>
        <div className={styles.heading}>
          <h1 className={styles.title}>Choose a new password</h1>
          <p className={styles.subtitle}>Use at least 8 characters to secure your account.</p>
        </div>
        <form onSubmit={handleSubmit} className={styles.form}>
          {error && <div className={styles.errorAlert} role="alert">{error}</div>}
          <div className="form-group">
            <label htmlFor="new-password" className="form-label">New password</label>
            <div className={styles.passwordField}>
              <input id="new-password" type={showPassword ? "text" : "password"} className="form-input" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="new-password" required disabled={loading} />
              <button type="button" className={styles.passwordToggle} onClick={() => setShowPassword((visible) => !visible)} aria-label={showPassword ? "Hide password" : "Show password"} aria-pressed={showPassword} disabled={loading}>{showPassword ? "Hide" : "Show"}</button>
            </div>
          </div>
          <div className="form-group">
            <label htmlFor="confirm-password" className="form-label">Confirm new password</label>
            <input id="confirm-password" type={showPassword ? "text" : "password"} className="form-input" value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} autoComplete="new-password" required disabled={loading} />
          </div>
          <button type="submit" className={`btn btn-primary ${styles.submitBtn}`} disabled={loading}>{loading ? "Updating password…" : "Update password"}</button>
        </form>
        <p className={styles.switchLink}><Link href="/login">Back to sign in</Link></p>
      </div>
  );
}

export default function ResetPasswordPage() {
  return (
    <div className={styles.page}>
      <Suspense>
        <ResetPasswordForm />
      </Suspense>
    </div>
  );
}
