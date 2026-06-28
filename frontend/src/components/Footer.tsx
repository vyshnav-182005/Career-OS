import Link from "next/link";
import styles from "./Footer.module.css";

const footerLinks = [
  {
    heading: "Product",
    links: [
      { label: "Features", href: "#features" },
      { label: "How it works", href: "#how-it-works" },
      { label: "Agents", href: "#agents" },
    ],
  },
  {
    heading: "Platform",
    links: [
      { label: "Sign up", href: "/register" },
      { label: "Login", href: "/login" },
      { label: "Dashboard", href: "/dashboard" },
    ],
  },
];

export default function Footer() {
  return (
    <footer className={styles.footer}>
      {/* CTA Banner */}
      <div className={styles.ctaBanner}>
        <div className="container">
          <div className={styles.ctaInner}>
            <div className={styles.ctaText}>
              <h2 className={styles.ctaTitle}>
                Ready to accelerate
                <span className="gradient-text"> your career?</span>
              </h2>
              <p className={styles.ctaSub}>
                Join CareerOS today — it&apos;s free to get started.
              </p>
            </div>
            <Link href="/register" className="btn btn-primary btn-lg">
              Get started free
              <svg width="18" height="18" viewBox="0 0 18 18" fill="none" aria-hidden="true">
                <path d="M3.75 9h10.5M9.75 4.5L14.25 9l-4.5 4.5" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </Link>
          </div>
        </div>
      </div>

      {/* Footer body */}
      <div className={styles.body}>
        <div className="container">
          <div className={styles.grid}>
            {/* Brand column */}
            <div className={styles.brand}>
              <Link href="/" className={styles.logo}>
                <svg width="28" height="28" viewBox="0 0 28 28" fill="none" aria-hidden="true">
                  <rect width="28" height="28" rx="8" fill="url(#footer-logo-grad)" />
                  <path d="M8 14L12 18L20 10" stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
                  <defs>
                    <linearGradient id="footer-logo-grad" x1="0" y1="0" x2="28" y2="28" gradientUnits="userSpaceOnUse">
                      <stop stopColor="#6366f1" />
                      <stop offset="1" stopColor="#06b6d4" />
                    </linearGradient>
                  </defs>
                </svg>
                <span className={styles.logoText}>Career<span className="gradient-text">OS</span></span>
              </Link>
              <p className={styles.brandDesc}>
                AI-powered career guidance platform. Analyze, match, and optimize
                your job search with intelligent agents.
              </p>
            </div>

            {/* Link columns */}
            {footerLinks.map((col) => (
              <div key={col.heading} className={styles.linkCol}>
                <h4 className={styles.colHeading}>{col.heading}</h4>
                <ul className={styles.linkList}>
                  {col.links.map((l) => (
                    <li key={l.label}>
                      <a href={l.href} className={styles.footerLink}>{l.label}</a>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>

          <div className={styles.bottom}>
            <p className={styles.copy}>
              © {new Date().getFullYear()} CareerOS. Built with AI.
            </p>
            <div className={styles.badges}>
              <span className={styles.techBadge}>Next.js</span>
              <span className={styles.techBadge}>Supabase</span>
              <span className={styles.techBadge}>Gemini AI</span>
            </div>
          </div>
        </div>
      </div>
    </footer>
  );
}
