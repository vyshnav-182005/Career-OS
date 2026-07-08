"use client";

import styles from "./Footer.module.css";

export default function Footer() {
  return (
    <footer className={styles.footer}>
      <div className="container">
        <div className={styles.inner}>
          <div className={styles.brand}>
            Career<span className="gradient-text">OS</span>
          </div>
          <div className={styles.copy}>
            © {new Date().getFullYear()} CareerOS
          </div>
        </div>
      </div>
    </footer>
  );
}
