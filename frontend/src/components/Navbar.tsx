"use client";

import Link from "next/link";
import { useState, useEffect } from "react";
import styles from "./Navbar.module.css";

export default function Navbar() {
  const [scrolled, setScrolled] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => {
    const handleScroll = () => setScrolled(window.scrollY > 20);
    window.addEventListener("scroll", handleScroll, { passive: true });
    return () => window.removeEventListener("scroll", handleScroll);
  }, []);

  return (
    <nav className={`${styles.navbar} ${scrolled ? styles.scrolled : ""}`}>
      <div className="container">
        <div className={styles.inner}>
          {/* Logo */}
          <Link href="/" className={styles.logo} aria-label="CareerOS Home">
            <span className={styles.logoIcon}>
              <svg width="28" height="28" viewBox="0 0 28 28" fill="none">
                <rect width="28" height="28" rx="8" fill="url(#logo-gradient)" />
                <path
                  d="M8 14L12 18L20 10"
                  stroke="white"
                  strokeWidth="2.5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
                <defs>
                  <linearGradient id="logo-gradient" x1="0" y1="0" x2="28" y2="28" gradientUnits="userSpaceOnUse">
                    <stop stopColor="#6366f1" />
                    <stop offset="1" stopColor="#06b6d4" />
                  </linearGradient>
                </defs>
              </svg>
            </span>
            <span className={styles.logoText}>
              Career<span className="gradient-text">OS</span>
            </span>
          </Link>

          {/* Desktop nav links */}
          <ul className={styles.navLinks}>
            <li><a href="#features" className={styles.navLink}>Features</a></li>
            <li><a href="#how-it-works" className={styles.navLink}>How it works</a></li>
            <li><a href="#agents" className={styles.navLink}>Agents</a></li>
          </ul>

          {/* CTA buttons */}
          <div className={styles.cta}>
            <Link href="/login" className="btn btn-ghost btn-sm">
              Sign in
            </Link>
            <Link href="/register" className="btn btn-primary btn-sm">
              Get started
            </Link>
          </div>

          {/* Mobile menu toggle */}
          <button
            id="mobile-menu-toggle"
            className={styles.menuToggle}
            onClick={() => setMenuOpen(!menuOpen)}
            aria-label="Toggle menu"
            aria-expanded={menuOpen}
          >
            <span className={`${styles.menuBar} ${menuOpen ? styles.open : ""}`} />
            <span className={`${styles.menuBar} ${menuOpen ? styles.open : ""}`} />
            <span className={`${styles.menuBar} ${menuOpen ? styles.open : ""}`} />
          </button>
        </div>
      </div>

      {/* Mobile menu */}
      {menuOpen && (
        <div className={styles.mobileMenu}>
          <a href="#features" className={styles.mobileLink} onClick={() => setMenuOpen(false)}>Features</a>
          <a href="#how-it-works" className={styles.mobileLink} onClick={() => setMenuOpen(false)}>How it works</a>
          <a href="#agents" className={styles.mobileLink} onClick={() => setMenuOpen(false)}>Agents</a>
          <div className={styles.mobileCta}>
            <Link href="/login" className="btn btn-ghost btn-sm" style={{ width: "100%" }}>Sign in</Link>
            <Link href="/register" className="btn btn-primary btn-sm" style={{ width: "100%" }}>Get started</Link>
          </div>
        </div>
      )}
    </nav>
  );
}
