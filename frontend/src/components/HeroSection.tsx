import Link from "next/link";
import styles from "./HeroSection.module.css";

export default function HeroSection() {
  return (
    <section className={styles.hero} id="hero">
      {/* Background gradient orbs */}
      <div className={styles.orb1} aria-hidden="true" />
      <div className={styles.orb2} aria-hidden="true" />
      <div className={styles.grid} aria-hidden="true" />

      <div className="container">
        <div className={styles.content}>
          {/* Badge */}
          <div className="badge badge-primary animate-fade-in-up">
            <svg width="12" height="12" viewBox="0 0 12 12" fill="none" aria-hidden="true">
              <circle cx="6" cy="6" r="4" fill="currentColor" />
            </svg>
            AI-Powered Career Guidance
          </div>

          {/* Headline */}
          <h1 className={`${styles.headline} animate-fade-in-up delay-100`}>
            Your career,
            <br />
            <span className="gradient-text">intelligently guided</span>
          </h1>

          {/* Subheadline */}
          <p className={`${styles.sub} animate-fade-in-up delay-200`}>
            CareerOS uses multi-agent AI to analyze your resume, match you with roles
            you&apos;ll love, and craft ATS-optimized applications — all in one platform.
          </p>

          {/* CTAs */}
          <div className={`${styles.actions} animate-fade-in-up delay-300`}>
            <Link href="/register" className="btn btn-primary btn-lg">
              Start for free
              <svg width="18" height="18" viewBox="0 0 18 18" fill="none" aria-hidden="true">
                <path d="M3.75 9h10.5M9.75 4.5L14.25 9l-4.5 4.5" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </Link>
            <a href="#how-it-works" className="btn btn-secondary btn-lg">
              See how it works
            </a>
          </div>

          {/* Social proof */}
          <div className={`${styles.socialProof} animate-fade-in-up delay-400`}>
            <div className={styles.avatars} aria-hidden="true">
              {["#6366f1", "#06b6d4", "#f59e0b", "#10b981"].map((color, i) => (
                <div key={i} className={styles.avatar} style={{ background: color, zIndex: 4 - i }} />
              ))}
            </div>
            <span className={styles.socialText}>
              Join <strong>thousands</strong> of professionals accelerating their careers
            </span>
          </div>
        </div>

        {/* Hero visual */}
        <div className={`${styles.visual} animate-fade-in-up delay-300`}>
          <div className={styles.dashboardCard}>
            <div className={styles.cardHeader}>
              <div className={styles.cardDots}>
                <span style={{ background: "#f87171" }} />
                <span style={{ background: "#fbbf24" }} />
                <span style={{ background: "#4ade80" }} />
              </div>
              <span className={styles.cardTitle}>Profile Analysis</span>
            </div>
            <div className={styles.cardBody}>
              <div className={styles.profileRow}>
                <div className={styles.profileAvatar}>
                  <svg width="28" height="28" viewBox="0 0 28 28" fill="none" aria-hidden="true">
                    <circle cx="14" cy="10" r="5" stroke="#6366f1" strokeWidth="1.5" />
                    <path d="M5 24c0-4.97 4.03-9 9-9s9 4.03 9 9" stroke="#6366f1" strokeWidth="1.5" strokeLinecap="round" />
                  </svg>
                </div>
                <div className={styles.profileInfo}>
                  <span className={styles.profileName}>Your Profile</span>
                  <span className={styles.profileRole}>Software Engineer</span>
                </div>
                <div className={styles.profileScore}>
                  <span className={styles.scoreValue}>87</span>
                  <span className={styles.scoreLabel}>Score</span>
                </div>
              </div>
              <div className={styles.skills}>
                {["React", "TypeScript", "Python", "FastAPI"].map((skill) => (
                  <span key={skill} className={styles.skillChip}>{skill}</span>
                ))}
              </div>
              <div className={styles.matches}>
                <div className={styles.matchHeader}>
                  <span>Top Job Matches</span>
                  <span className={styles.matchCount}>12 found</span>
                </div>
                {[
                  { title: "Senior Frontend Engineer", company: "Stripe", match: 94 },
                  { title: "Full Stack Developer", company: "Vercel", match: 88 },
                  { title: "Software Engineer II", company: "Linear", match: 82 },
                ].map((job) => (
                  <div key={job.title} className={styles.jobRow}>
                    <div className={styles.jobInfo}>
                      <span className={styles.jobTitle}>{job.title}</span>
                      <span className={styles.jobCompany}>{job.company}</span>
                    </div>
                    <div className={styles.matchBar}>
                      <div className={styles.matchFill} style={{ width: `${job.match}%` }} />
                    </div>
                    <span className={styles.matchPct}>{job.match}%</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
          {/* Floating badge */}
          <div className={styles.floatingBadge}>
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
              <path d="M8 2l1.5 3 3.5.5-2.5 2.5.5 3.5L8 10l-3 1.5.5-3.5L3 5.5 6.5 5 8 2z" fill="#f59e0b" />
            </svg>
            <span>ATS Score: 94%</span>
          </div>
        </div>
      </div>
    </section>
  );
}
