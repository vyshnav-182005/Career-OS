"use client";

import { useState, useEffect, useMemo } from "react";
import type { Job } from "@/lib/types/job";
import { normalizeRecommendedJob, jobMatchPercent } from "@/lib/types/job";
import { summarizeJobDescription } from "@/lib/utils/jobText";
import { submitJobFeedback, type JobFeedbackVote } from "@/lib/api/jobFeedback";
import JobDetailModal from "./JobDetailModal";
import styles from "./RecommendedJobs.module.css";

interface RecommendedJobsProps {
  hasProfile: boolean;
}

interface FeedbackState {
  vote: JobFeedbackVote | null;
  pending: boolean;
  error: string | null;
}

const VERDICT_LABEL: Record<string, string> = {
  strong: "Strong Match",
  possible: "Possible Match",
};

/**
 * Jobs shown per page. The backend returns several pages' worth in a single
 * request, so paging is instant and never re-runs the LLM re-ranker.
 */
const PAGE_SIZE = 10;
/** Matches requested from the API — enough for a few pages of results. */
const FETCH_LIMIT = 30;

function scoreTier(score: number): "good" | "fair" | "poor" {
  if (score >= 75) return "good";
  if (score >= 50) return "fair";
  return "poor";
}

export default function RecommendedJobs({ hasProfile }: RecommendedJobsProps) {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedJob, setSelectedJob] = useState<Job | null>(null);
  const [feedback, setFeedback] = useState<Record<string, FeedbackState>>({});
  const [page, setPage] = useState(0);

  useEffect(() => {
    if (!hasProfile) return;

    const controller = new AbortController();

    const fetchRecommended = async () => {
      setLoading(true);
      setError(null);
      try {
        const res = await fetch(`/api/jobs/recommended?limit=${FETCH_LIMIT}`, {
          signal: controller.signal,
        });
        if (!res.ok) throw new Error("Failed to fetch recommended jobs");
        const data = await res.json();
        const rawJobs: unknown[] = data.data || [];
        setJobs(rawJobs.map(normalizeRecommendedJob));
        setPage(0);
      } catch (err: unknown) {
        const isAbort = err instanceof DOMException && err.name === "AbortError";
        if (!isAbort) setError(err instanceof Error ? err.message : "Failed to fetch recommended jobs");
      } finally {
        setLoading(false);
      }
    };

    fetchRecommended();
    return () => controller.abort();
  }, [hasProfile]);

  // Deduplicate by title + company. Memoized so a page turn doesn't rebuild it.
  const uniqueJobs = useMemo(() => {
    const seen = new Set<string>();
    const result: Job[] = [];
    for (const job of jobs) {
      const key = `${job.title.toLowerCase()}-${job.company.toLowerCase()}`;
      if (!seen.has(key)) {
        seen.add(key);
        result.push(job);
      }
    }
    return result;
  }, [jobs]);

  const pageCount = Math.max(1, Math.ceil(uniqueJobs.length / PAGE_SIZE));
  // Clamped on read rather than stored, so a shrinking result set can never
  // strand the user on a page that no longer exists.
  const currentPage = Math.min(page, pageCount - 1);
  const pageStart = currentPage * PAGE_SIZE;
  const visibleJobs = uniqueJobs.slice(pageStart, pageStart + PAGE_SIZE);
  const hasPrevious = currentPage > 0;
  const hasNext = currentPage < pageCount - 1;

  function goToPage(next: number) {
    setPage(Math.max(0, Math.min(next, pageCount - 1)));
  }

  async function handleVote(job: Job, vote: JobFeedbackVote) {
    const previous = feedback[job.id];
    // Clicking the active vote again clears it (toggle off); otherwise it switches.
    const nextVote = previous?.vote === vote ? null : vote;

    setFeedback((prev) => ({ ...prev, [job.id]: { vote: nextVote, pending: true, error: null } }));

    if (nextVote === null) {
      // Nothing to persist for a cleared vote yet — the backend only stores up/down.
      setFeedback((prev) => ({ ...prev, [job.id]: { vote: null, pending: false, error: null } }));
      return;
    }

    try {
      await submitJobFeedback(job.id, nextVote);
      setFeedback((prev) => ({ ...prev, [job.id]: { vote: nextVote, pending: false, error: null } }));
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Failed to save feedback";
      setFeedback((prev) => ({
        ...prev,
        [job.id]: { vote: previous?.vote ?? null, pending: false, error: message },
      }));
    }
  }

  const noProfileEmptyState = (
    <div className={styles.emptyState}>
      <div className={styles.emptyIcon}>✨</div>
      <h3>No recommendations yet</h3>
      <p>Upload or update your resume to start seeing personalized matches here.</p>
    </div>
  );

  const noMatchesYetEmptyState = (
    <div className={styles.emptyState}>
      <div className={styles.emptyIcon}>🔎</div>
      <h3>Still sourcing roles for you</h3>
      <p>
        Your profile is set, but we haven&apos;t found jobs in your target roles yet.
        We&apos;re actively pulling in new postings — check back soon.
      </p>
    </div>
  );

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <div className={styles.headerText}>
          <h2>For You</h2>
          <p>Curated matches based on your unique profile</p>
        </div>
        {uniqueJobs.length > 0 && (
          <span className={styles.resultCount}>
            {uniqueJobs.length} {uniqueJobs.length === 1 ? "match" : "matches"}
          </span>
        )}
      </div>

      {!hasProfile ? (
        noProfileEmptyState
      ) : loading ? (
        <div className={styles.loadingState}>
          <div className={styles.spinner}></div>
          <p>Analyzing profile and sourcing roles...</p>
        </div>
      ) : error ? (
        <div className={styles.error}>{error}</div>
      ) : uniqueJobs.length === 0 ? (
        noMatchesYetEmptyState
      ) : (
        <>
          <div className={styles.jobGrid}>
            {visibleJobs.map((job) => {
              const fb = feedback[job.id];
              const matchPercent = jobMatchPercent(job);
              const isEstimate = job.ats_score_source !== "analyzed";
              const preview = summarizeJobDescription(job.description, 150);

              return (
                <div
                  key={`${job.provider}-${job.provider_job_id}`}
                  className={styles.jobCard}
                  role="button"
                  tabIndex={0}
                  aria-label={`View details for ${job.title} at ${job.company}`}
                  onClick={() => setSelectedJob(job)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      setSelectedJob(job);
                    }
                  }}
                >
                  <div className={styles.jobCardGlow}></div>
                  <div className={styles.jobCardInner}>
                    <div className={styles.jobHeader}>
                      <div className={styles.jobIdentity}>
                        <h3 className={styles.jobTitle}>{job.title}</h3>
                        <div className={styles.jobCompany}>
                          <span className={styles.companyName}>{job.company}</span>
                          <span className={styles.dotSeparator}>•</span>
                          <span className={styles.location}>{job.location || "Remote"}</span>
                        </div>
                      </div>

                      {matchPercent !== null && (
                        <div
                          className={`${styles.atsScore} ${styles[scoreTier(matchPercent)]}`}
                          title={
                            isEstimate
                              ? "Estimated ATS match against your resume. Open the job for a full analysis."
                              : "ATS match from your completed resume analysis for this job."
                          }
                        >
                          <span className={styles.atsValue}>
                            {isEstimate ? "~" : ""}
                            {matchPercent}
                            <span className={styles.atsPercentSign}>%</span>
                          </span>
                          <span className={styles.atsLabel}>ATS Match</span>
                        </div>
                      )}
                    </div>

                    <div className={styles.jobTags}>
                      {job.verdict && VERDICT_LABEL[job.verdict] && (
                        <span className={`${styles.matchBadge} ${styles[`verdict-${job.verdict}`] || ""}`}>
                          {VERDICT_LABEL[job.verdict]}
                        </span>
                      )}
                      <span className={styles.tag}>{job.employment_type || "Full-time"}</span>
                      {job.salary && <span className={styles.tagSalary}>{job.salary}</span>}
                      {job.provider && <span className={styles.providerBadge}>via {job.provider}</span>}
                    </div>

                    {job.reason ? (
                      <p className={styles.matchReason}>{job.reason}</p>
                    ) : preview ? (
                      <p className={styles.jobDescription}>{preview}</p>
                    ) : null}

                    {(job.matched_skills?.length || job.missing_skills?.length) ? (
                      <div className={styles.skillChipsSection}>
                        {job.matched_skills && job.matched_skills.length > 0 && (
                          <div className={styles.chipRow}>
                            {job.matched_skills.slice(0, 5).map((skill) => (
                              <span key={`m-${skill}`} className={styles.matchedChip}>{skill}</span>
                            ))}
                          </div>
                        )}
                        {job.missing_skills && job.missing_skills.length > 0 && (
                          <div className={styles.chipRow}>
                            <span className={styles.missingLabel}>You&apos;d need:</span>
                            {job.missing_skills.slice(0, 4).map((skill) => (
                              <span key={`n-${skill}`} className={styles.missingChip}>{skill}</span>
                            ))}
                          </div>
                        )}
                      </div>
                    ) : null}

                    {/* Nested controls stop propagation so they never also fire
                        the card's own "open details" handler. */}
                    <div className={styles.feedbackRow} onClick={(e) => e.stopPropagation()}>
                      <button
                        type="button"
                        className={`${styles.feedbackBtn} ${fb?.vote === "up" ? styles.feedbackBtnActive : ""}`}
                        aria-label="This recommendation was helpful"
                        aria-pressed={fb?.vote === "up"}
                        disabled={fb?.pending}
                        onClick={() => handleVote(job, "up")}
                      >
                        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M14 9V5a3 3 0 0 0-3-3l-4 9v11h11.28a2 2 0 0 0 2-1.7l1.38-9a2 2 0 0 0-2-2.3zM7 22H4a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2h3"/></svg>
                      </button>
                      <button
                        type="button"
                        className={`${styles.feedbackBtn} ${fb?.vote === "down" ? styles.feedbackBtnActive : ""}`}
                        aria-label="This recommendation was not helpful"
                        aria-pressed={fb?.vote === "down"}
                        disabled={fb?.pending}
                        onClick={() => handleVote(job, "down")}
                      >
                        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M10 15v4a3 3 0 0 0 3 3l4-9V2H5.72a2 2 0 0 0-2 1.7l-1.38 9a2 2 0 0 0 2 2.3zm7-13h3a2 2 0 0 1 2 2v7a2 2 0 0 1-2 2h-3"/></svg>
                      </button>
                      {fb?.error && <span className={styles.feedbackError}>{fb.error}</span>}
                    </div>

                    <div className={styles.jobFooter} onClick={(e) => e.stopPropagation()}>
                      <button
                        type="button"
                        className={styles.detailsBtn}
                        onClick={() => setSelectedJob(job)}
                      >
                        View Details
                      </button>
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
              );
            })}
          </div>

          {pageCount > 1 && (
            <div className={styles.pagination}>
              <div className={styles.paginationNav}>
                <button
                  type="button"
                  className={styles.pageBtn}
                  onClick={() => goToPage(currentPage - 1)}
                  disabled={!hasPrevious}
                  aria-label="Previous page of jobs"
                >
                  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="15 18 9 12 15 6"/></svg>
                  Previous
                </button>

                <span className={styles.pageStatus} aria-live="polite">
                  <span>Page {currentPage + 1} of {pageCount}</span>
                  <span className={styles.pageRange}>
                    Showing {pageStart + 1}–{pageStart + visibleJobs.length} of {uniqueJobs.length}
                  </span>
                </span>

                <button
                  type="button"
                  className={styles.pageBtn}
                  onClick={() => goToPage(currentPage + 1)}
                  disabled={!hasNext}
                  aria-label="Next page of jobs"
                >
                  Next
                  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="9 18 15 12 9 6"/></svg>
                </button>
              </div>

              {hasNext && (
                <button type="button" className={styles.showMoreBtn} onClick={() => goToPage(currentPage + 1)}>
                  Show More
                </button>
              )}
            </div>
          )}
        </>
      )}

      {selectedJob && (
        <JobDetailModal
          job={selectedJob}
          hasProfile={hasProfile}
          onClose={() => setSelectedJob(null)}
        />
      )}
    </div>
  );
}
