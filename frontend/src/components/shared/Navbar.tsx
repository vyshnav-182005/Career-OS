"use client";

import Link from "next/link";
import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { useSession } from "next-auth/react";
import ThemeToggle from "./ThemeToggle";
import styles from "./Navbar.module.css";

export default function Navbar() {
  const router = useRouter();
  const [scrolled, setScrolled] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const { data: session } = useSession();
  const user = session?.user ?? null;

  useEffect(() => {
    const handleScroll = () => setScrolled(window.scrollY > 20);
    window.addEventListener("scroll", handleScroll, { passive: true });

    const handlePageShow = (event: PageTransitionEvent) => {
      if (event.persisted) {
        router.refresh();
      }
    };
    window.addEventListener("pageshow", handlePageShow);

    return () => {
      window.removeEventListener("scroll", handleScroll);
      window.removeEventListener("pageshow", handlePageShow);
    };
  }, [router]);

  return (
    <nav className={`${styles.navbar} ${scrolled ? styles.scrolled : ""}`}>
      <div className="container">
        <div className={styles.inner}>
          <Link href="/" className={styles.logo} aria-label="CareerOS Home">
            <span className={styles.logoText}>
              Career<span className="gradient-text">OS</span>
            </span>
          </Link>

          <div className={styles.cta}>
            <ThemeToggle />
            
            <ul className={styles.navLinks}>
              <li><a href="#features" className={styles.navLink}>Features</a></li>
              <li><a href="#how-it-works" className={styles.navLink}>How it works</a></li>
            </ul>

            <div className={styles.authButtons}>
              {user ? (
                <>
                  <Link href="/login" className="btn btn-ghost btn-sm">
                    Log in
                  </Link>
                  <Link href="/dashboard" className="btn btn-primary btn-sm">
                    Go to Dashboard
                  </Link>
                </>
              ) : (
                <>
                  <Link href="/login" className="btn btn-ghost btn-sm">
                    Log in
                  </Link>
                  <Link href="/register" className="btn btn-primary btn-sm">
                    Get started
                  </Link>
                </>
              )}
            </div>
          </div>

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

      {menuOpen && (
        <div className={styles.mobileMenu}>
          <a href="#features" className={styles.mobileLink} onClick={() => setMenuOpen(false)}>Features</a>
          <a href="#how-it-works" className={styles.mobileLink} onClick={() => setMenuOpen(false)}>How it works</a>
          <div className={styles.mobileThemeToggle}>
            <ThemeToggle />
            <span className={styles.mobileThemeText}>Toggle theme</span>
          </div>
          <div className={styles.mobileCta}>
            {user ? (
              <>
                <Link href="/login" className="btn btn-ghost btn-sm" style={{ width: "100%", marginBottom: "0.5rem" }}>Log in</Link>
                <Link href="/dashboard" className="btn btn-primary btn-sm" style={{ width: "100%" }}>Go to Dashboard</Link>
              </>
            ) : (
              <>
                <Link href="/login" className="btn btn-ghost btn-sm" style={{ width: "100%", marginBottom: "0.5rem" }}>Log in</Link>
                <Link href="/register" className="btn btn-primary btn-sm" style={{ width: "100%" }}>Get started</Link>
              </>
            )}
          </div>
        </div>
      )}
    </nav>
  );
}
