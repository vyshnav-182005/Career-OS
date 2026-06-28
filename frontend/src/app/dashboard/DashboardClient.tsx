"use client";

import { useState } from "react";
import Link from "next/link";
import type { ParsedResume, ProfileIntelligence } from "@/lib/types/resume";
import ResumeUploader from "@/components/ResumeUploader";
import ParsedResumeView from "@/components/ParsedResumeView";
import ProfileIntelligenceView from "@/components/ProfileIntelligenceView";
import styles from "./dashboard.module.css";

interface DashboardClientProps {
  displayName: string;
  avatarChar: string;
}

export default function DashboardClient({ displayName, avatarChar }: DashboardClientProps) {
  const [parsedResume, setParsedResume] = useState<ParsedResume | null>(null);
  const [parsedFilename, setParsedFilename] = useState<string>("");
  const [profileIntelligence, setProfileIntelligence] = useState<ProfileIntelligence | null>(null);

  function handleParsed(resume: ParsedResume, filename: string, intelligence: ProfileIntelligence | null) {
    setParsedResume(resume);
    setParsedFilename(filename);
    setProfileIntelligence(intelligence);
  }

  function handleReset() {
    setParsedResume(null);
    setParsedFilename("");
    setProfileIntelligence(null);
  }

  return (
    <div className={styles.page}>
      <aside className={styles.sidebar}>
        <div className={styles.sidebarLogo}>
          <svg width="28" height="28" viewBox="0 0 28 28" fill="none" aria-hidden="true">
            <rect width="28" height="28" rx="8" fill="url(#dash-logo-grad)" />
            <path d="M8 14L12 18L20 10" stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
            <defs>
              <linearGradient id="dash-logo-grad" x1="0" y1="0" x2="28" y2="28" gradientUnits="userSpaceOnUse">
                <stop stopColor="#6366f1" />
                <stop offset="1" stopColor="#06b6d4" />
              </linearGradient>
            </defs>
          </svg>
          <span className={styles.sidebarLogoText}>Career<span className="gradient-text">OS</span></span>
        </div>

        <nav className={styles.sidebarNav}>
          {[
            { icon: "🏠", label: "Overview", active: true },
            { icon: "📄", label: "My Resumes", active: false },
            { icon: "🎯", label: "Job Matches", active: false },
            { icon: "⚡", label: "Optimize Resume", active: false },
            { icon: "👤", label: "Profile", active: false },
          ].map((item) => (
            <div
              key={item.label}
              className={`${styles.navItem} ${item.active ? styles.navItemActive : ""}`}
            >
              <span className={styles.navIcon}>{item.icon}</span>
              <span>{item.label}</span>
            </div>
          ))}
        </nav>

        <div className={styles.sidebarBottom}>
          <form action="/auth/signout" method="post">
            <button type="submit" className={styles.signoutBtn}>Sign out</button>
          </form>
        </div>
      </aside>

      <main className={styles.main}>
        <header className={styles.header}>
          <div>
            <h1 className={styles.greeting}>Welcome back, {displayName} 👋</h1>
            <p className={styles.headerSub}>Here&apos;s your career intelligence dashboard</p>
          </div>
          <div className={styles.userBadge}>
            <div className={styles.userAvatar} aria-hidden="true">{avatarChar}</div>
          </div>
        </header>

        {/* Stats row — shown when resume is parsed */}
        {parsedResume && (
          <div className={styles.statsRow}>
            {profileIntelligence ? (
              <>
                <StatCard label="Career Level" value={profileIntelligence.career_level} icon="⭐" />
                <StatCard label="Profile Score" value={`${profileIntelligence.profile_completeness.overall_score}%`} icon="📈" />
                <StatCard label="Experience" value={`${profileIntelligence.total_years_experience} Yrs`} icon="💼" />
                <StatCard label="Job Matches" value={`${profileIntelligence.inferred_job_roles.length} roles`} icon="🎯" />
              </>
            ) : (
              <>
                <StatCard label="Experience" value={`${parsedResume.experience.length} roles`} icon="💼" />
                <StatCard label="Skills" value={`${parsedResume.skills.reduce((acc, c) => acc + c.skills.length, 0)} found`} icon="⚡" />
                <StatCard label="Projects" value={`${parsedResume.projects.length} listed`} icon="🚀" />
                <StatCard label="Education" value={`${parsedResume.education.length} entries`} icon="🎓" />
              </>
            )}
          </div>
        )}

        {/* Top cards — hide upload card when parsed */}
        {!parsedResume && (
          <div className={styles.grid}>
            {[
              {
                title: "Profile Score",
                desc: "Your enriched career profile will appear here once you upload a resume.",
                icon: "⚡",
                color: "#06b6d4",
                tag: "Coming soon",
                tagColor: "rgba(6,182,212,0.1)",
                tagBorder: "rgba(6,182,212,0.25)",
                tagText: "#22d3ee",
              },
              {
                title: "Job Matches",
                desc: "AI-ranked job opportunities aligned with your skills and goals.",
                icon: "🎯",
                color: "#f59e0b",
                tag: "Coming soon",
                tagColor: "rgba(245,158,11,0.1)",
                tagBorder: "rgba(245,158,11,0.25)",
                tagText: "#fbbf24",
              },
            ].map((card) => (
              <div key={card.title} className={styles.dashCard}>
                <div className={styles.dashCardTop}>
                  <span className={styles.dashCardIcon}>{card.icon}</span>
                  <span
                    className={styles.dashCardTag}
                    style={{
                      background: card.tagColor,
                      border: `1px solid ${card.tagBorder}`,
                      color: card.tagText,
                    }}
                  >
                    {card.tag}
                  </span>
                </div>
                <h3 className={styles.dashCardTitle}>{card.title}</h3>
                <p className={styles.dashCardDesc}>{card.desc}</p>
              </div>
            ))}
          </div>
        )}

        {/* Upload / Result area */}
        <div className={styles.uploadSection}>
          {parsedResume ? (
            <>
              <ParsedResumeView
                resume={parsedResume}
                filename={parsedFilename}
                onReset={handleReset}
              />
              {profileIntelligence && (
                <ProfileIntelligenceView intelligence={profileIntelligence} />
              )}
            </>
          ) : (
            <div className={styles.uploadCard}>
              <div className={styles.uploadCardHeader}>
                <div className={styles.uploadCardMeta}>
                  <span className={styles.uploadCardIcon}>📤</span>
                  <div>
                    <h2 className={styles.uploadCardTitle}>Upload Resume</h2>
                    <p className={styles.uploadCardDesc}>Parse your resume with AI and build your career profile</p>
                  </div>
                </div>
                <span
                  className={styles.dashCardTag}
                  style={{
                    background: "rgba(99,102,241,0.15)",
                    border: "1px solid rgba(99,102,241,0.3)",
                    color: "#818cf8",
                  }}
                >
                  Start here
                </span>
              </div>
              <ResumeUploader onParsed={handleParsed} />
            </div>
          )}
        </div>

        <div className={styles.buildingNotice}>
          <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
            <circle cx="10" cy="10" r="8" stroke="currentColor" strokeWidth="1.5" />
            <path d="M10 6v4l3 2" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
          </svg>
          <span>
            CareerOS is actively being built.{" "}
            <Link href="/">Return to home</Link> to learn more.
          </span>
        </div>
      </main>
    </div>
  );
}

function StatCard({ label, value, icon }: { label: string; value: string; icon: string }) {
  return (
    <div className={styles.statCard}>
      <span className={styles.statIcon}>{icon}</span>
      <div>
        <p className={styles.statValue}>{value}</p>
        <p className={styles.statLabel}>{label}</p>
      </div>
    </div>
  );
}
