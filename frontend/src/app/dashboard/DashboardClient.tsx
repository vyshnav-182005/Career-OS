"use client";

import { useState, useEffect } from "react";
import { createClient } from "@/lib/supabase/client";
import type { ParsedResume, ProfileIntelligence } from "@/lib/types/resume";
import ResumeUploader from "@/components/ResumeUploader";
import ProfileView from "@/components/ProfileView";
import ThemeToggle from "@/components/ThemeToggle";
import styles from "./dashboard.module.css";

interface DashboardClientProps {
  displayName: string;
  avatarChar: string;
  initialProfileIntelligence?: ProfileIntelligence | null;
  initialFilename?: string | null;
  initialResumeUrl?: string | null;
}

export default function DashboardClient({ 
  displayName, 
  avatarChar,
  initialProfileIntelligence,
  initialFilename,
  initialResumeUrl
}: DashboardClientProps) {
  const [activeTab, setActiveTab] = useState("Overview");
  const [parsedResume, setParsedResume] = useState<ParsedResume | null>(initialProfileIntelligence?.original_resume || null);
  const [parsedFilename, setParsedFilename] = useState<string>(initialFilename || "");
  const [profileIntelligence, setProfileIntelligence] = useState<ProfileIntelligence | null>(initialProfileIntelligence || null);
  const [resumeUrl, setResumeUrl] = useState<string | null>(initialResumeUrl || null);
  const [isPolling, setIsPolling] = useState(false);

  useEffect(() => {
    if (!isPolling) return;
    
    const supabase = createClient();
    const interval = setInterval(async () => {
      const { data: { user } } = await supabase.auth.getUser();
      if (!user) return;
      
      const { data } = await supabase
        .from('profiles')
        .select('profile_data, resume_url')
        .eq('user_id', user.id)
        .single();
      
      if (data?.resume_url) {
        setResumeUrl(data.resume_url);
      }
      
      if (data?.profile_data) {
        const pd = data.profile_data as ProfileIntelligence;
        if ((pd.strengths && pd.strengths.length > 0) || (pd.preferred_job_roles && pd.preferred_job_roles.length > 0)) {
          setProfileIntelligence(pd);
          if (pd.original_resume) {
            setParsedResume(pd.original_resume);
          }
          setIsPolling(false);
        }
      }
    }, 3000);
    
    return () => clearInterval(interval);
  }, [isPolling]);

  function handleParsed(resume: ParsedResume, filename: string, intelligence: ProfileIntelligence | null) {
    setParsedResume(resume);
    setParsedFilename(filename);
    setProfileIntelligence(intelligence);
    setIsPolling(true);
  }

  function handleReset() {
    setParsedResume(null);
    setParsedFilename("");
    setProfileIntelligence(null);
    setResumeUrl(null);
  }

  const isPdf = resumeUrl?.toLowerCase().endsWith(".pdf") || resumeUrl?.includes(".pdf?");

  const navItems = [
    { label: "Overview", icon: (
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/></svg>
    )},
    { label: "My Resume", icon: (
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>
    )},
  ];

  return (
    <div className={styles.page}>
      <aside className={styles.sidebar}>
        <div className={styles.sidebarLogo}>
          <span className={styles.logoText}>Career<span className="gradient-text">OS</span></span>
        </div>

        <nav className={styles.sidebarNav}>
          {navItems.map((item) => (
            <div
              key={item.label}
              className={`${styles.navItem} ${activeTab === item.label ? styles.navItemActive : ""}`}
              onClick={() => setActiveTab(item.label)}
              style={{ cursor: "pointer" }}
            >
              <span className={styles.navIcon}>{item.icon}</span>
              <span>{item.label}</span>
            </div>
          ))}
        </nav>

        <div className={styles.sidebarBottom}>
          <div className={styles.sidebarBottomRow}>
            <ThemeToggle />
          </div>
          <form action="/auth/signout" method="post">
            <button type="submit" className={styles.signoutBtn}>Sign out</button>
          </form>
        </div>
      </aside>

      <main className={styles.main}>
        <header className={styles.header}>
          <div>
            <h1 className={styles.greeting}>Welcome back, {displayName}</h1>
            <p className={styles.headerSub}>Your career intelligence dashboard</p>
          </div>
          <div className={styles.userBadge}>
            <div className={styles.userAvatar} aria-hidden="true">{avatarChar}</div>
          </div>
        </header>

        {/* Overview Tab */}
        {activeTab === "Overview" && (
          <div className={styles.overviewSection}>
            {!parsedResume ? (
              <div className={styles.uploadCard}>
                <div className={styles.uploadCardHeader}>
                  <div>
                    <h2 className={styles.uploadCardTitle}>Upload Resume</h2>
                    <p className={styles.uploadCardDesc}>Parse your resume with AI to build your career profile</p>
                  </div>
                </div>
                <ResumeUploader onParsed={handleParsed} />
              </div>
            ) : (
              <>
                {isPolling && !profileIntelligence && (
                  <div className={styles.pollingIndicator}>
                    <div className={styles.pollingDot} />
                    <span>Analyzing your profile...</span>
                  </div>
                )}
                
                <ProfileView
                  resume={parsedResume}
                  filename={parsedFilename}
                  intelligence={profileIntelligence}
                  onReset={handleReset}
                />
              </>
            )}
          </div>
        )}

        {/* My Resume Tab */}
        {activeTab === "My Resume" && (
          <div className={styles.myResumeSection}>
            {resumeUrl ? (
              isPdf ? (
                <div className={styles.pdfViewerContainer}>
                  <div className={styles.pdfViewerHeader}>
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
                    <strong>{parsedFilename || "Your Resume"}</strong>
                  </div>
                  <iframe src={resumeUrl} className={styles.pdfViewer} title="Resume PDF" />
                </div>
              ) : (
                <div className={styles.pdfViewerContainer} style={{ justifyContent: 'center', alignItems: 'center' }}>
                  <div className={styles.pdfViewerHeader} style={{ width: '100%', borderBottom: 'none', justifyContent: 'center' }}>
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
                    <strong>{parsedFilename || "Your Resume"}</strong>
                  </div>
                  <p style={{ color: 'var(--color-text-muted)', marginBottom: '24px' }}>Cannot preview DOCX files in browser.</p>
                  <a href={resumeUrl} download className={styles.downloadLink}>
                    Download Resume
                  </a>
                </div>
              )
            ) : (
              <div className={styles.uploadCard}>
                <div className={styles.uploadCardHeader}>
                  <div>
                    <h2 className={styles.uploadCardTitle}>Upload Resume</h2>
                    <p className={styles.uploadCardDesc}>Parse your resume with AI to build your career profile</p>
                  </div>
                </div>
                <ResumeUploader onParsed={handleParsed} />
              </div>
            )}
          </div>
        )}
      </main>
    </div>
  );
}
