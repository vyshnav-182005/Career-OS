"use client";

import Link from "next/link";
import styles from "./HeroSection.module.css";

export default function HeroSection() {
  return (
    <section className={styles.hero}>
      <div className="container">
        <div className={styles.inner}>
          <h1 className={styles.title}>
            Your Career <br />
            <span className="gradient-text">powered by AI</span>
          </h1>
          <p className={styles.subtitle}>
            Upload your resume. Get AI-powered insights, job matches, and optimized applications in seconds.
          </p>
          <div className={styles.cta}>
            <Link href="/register" className="btn btn-primary btn-lg">
              Get started
            </Link>
            <a href="#features" className="btn btn-secondary btn-lg">
              Learn more
            </a>
          </div>
        </div>
      </div>
    </section>
  );
}
