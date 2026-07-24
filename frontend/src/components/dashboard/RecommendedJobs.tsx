"use client";

import { useState, useEffect } from "react";
import styles from "./RecommendedJobs.module.css";

interface Job {
  id: string;
  title: string;
  company: string;
  location: string | null;
  description: string | null;
  employment_type: string | null;
  salary: string | null;
  posted_date: string | null;
  provider: string;
  provider_job_id: string;
  raw_payload: any;
  similarity?: number;
  url?: string;
}

interface RecommendedJobsProps {
  userId: string;
}

export default function RecommendedJobs({ userId }: RecommendedJobsProps) {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchRecommended = async () => {
      setLoading(true);
      setError(null);
      try {
        const res = await fetch(`http://localhost:8000/jobs/recommended?user_id=${userId}`);
        if (!res.ok) throw new Error("Failed to fetch recommended jobs");
        const data = await res.json();
        setJobs(data.data || []);
      } catch (err: any) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };
    if (userId) {
      fetchRecommended();
    }
  }, [userId]);

  // Deduplicate jobs by title + company on render
  const uniqueJobs: Job[] = [];
  const seen = new Set<string>();
  
  for (const job of jobs) {
    const key = `${job.title.toLowerCase()}-${job.company.toLowerCase()}`;
    if (!seen.has(key)) {
      seen.add(key);
      uniqueJobs.push(job);
    }
  }

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <div className={styles.headerText}>
          <h2>For You</h2>
          <p>Curated matches based on your unique profile</p>
        </div>
      </div>

      {loading ? (
        <div className={styles.loadingState}>
          <div className={styles.spinner}></div>
          <p>Analyzing profile and sourcing roles...</p>
        </div>
      ) : error ? (
        <div className={styles.error}>{error}</div>
      ) : (
        <div className={styles.jobGrid}>
          {uniqueJobs.length === 0 ? (
            <div className={styles.emptyState}>
              <div className={styles.emptyIcon}>✨</div>
              <h3>No recommendations yet</h3>
              <p>Upload or update your resume to start seeing personalized matches here.</p>
            </div>
          ) : (
            uniqueJobs.map(job => (
              <div key={`${job.provider}-${job.provider_job_id}`} className={styles.jobCard}>
                <div className={styles.jobCardGlow}></div>
                <div className={styles.jobCardInner}>
                  <div className={styles.jobHeader}>
                    <div className={styles.jobTitleWrapper}>
                      <h3 className={styles.jobTitle}>{job.title}</h3>
                      {job.similarity !== undefined && (
                        <span className={styles.matchBadge}>
                          {(job.similarity * 100).toFixed(0)}% Match
                        </span>
                      )}
                    </div>
                    {job.provider && (
                      <span className={styles.providerBadge}>
                        via {job.provider}
                      </span>
                    )}
                  </div>
                  <div className={styles.jobCompany}>
                    <span className={styles.companyName}>{job.company}</span>
                    <span className={styles.dotSeparator}>•</span>
                    <span className={styles.location}>{job.location || "Remote"}</span>
                  </div>
                  
                  <div className={styles.jobTags}>
                    <span className={styles.tag}>{job.employment_type || "Full-time"}</span>
                    {job.salary && <span className={styles.tagSalary}>{job.salary}</span>}
                  </div>
                  
                  {job.description && (
                    <p className={styles.jobDescription}>
                      {job.description
                        .replace(/(<([^>]+)>)/gi, "")
                        .replace(/&nbsp;/g, " ")
                        .replace(/&amp;/g, "&")
                        .replace(/&quot;/g, '"')
                        .replace(/&lt;/g, "<")
                        .replace(/&gt;/g, ">")
                        .replace(/&#39;/g, "'")
                        .trim()
                        .substring(0, 140)}...
                    </p>
                  )}
                  
                  <div className={styles.jobFooter}>
                    {job.url || job.raw_payload?.redirect_url || job.raw_payload?.url || job.raw_payload?.link ? (
                      <a href={job.url || job.raw_payload?.redirect_url || job.raw_payload?.url || job.raw_payload?.link} target="_blank" rel="noopener noreferrer" className={styles.applyBtn}>
                        Apply Now
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="5" y1="12" x2="19" y2="12"></line><polyline points="12 5 19 12 12 19"></polyline></svg>
                      </a>
                    ) : (
                      <button className={styles.applyBtn} disabled>Apply (Link N/A)</button>
                    )}
                  </div>
                </div>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}
