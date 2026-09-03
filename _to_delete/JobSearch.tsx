"use client";

import { useState, useEffect, useRef, FormEvent } from "react";
import type { Job } from "@/lib/types/job";
import { summarizeJobDescription } from "@/lib/utils/jobText";
import JobDetailModal from "./JobDetailModal";
import styles from "./JobSearch.module.css";

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || "http://127.0.0.1:8000";
const PAGE_SIZE = 20;

interface JobSearchProps {
  hasProfile: boolean;
}

export default function JobSearch({ hasProfile }: JobSearchProps) {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [ingesting, setIngesting] = useState(false);
  const [stats, setStats] = useState<any>(null);
  const [selectedJob, setSelectedJob] = useState<Job | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const fetchJobs = async (query = "", offset = 0) => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    if (offset === 0) {
      setLoading(true);
    } else {
      setLoadingMore(true);
    }
    setError(null);
    try {
      const params = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String(offset) });
      if (query) params.set("title", query);
      const res = await fetch(`${BACKEND_URL}/jobs?${params.toString()}`, { signal: controller.signal });
      if (!res.ok) throw new Error("Failed to fetch jobs");
      const data = await res.json();
      const page: Job[] = data.data || [];
      setJobs(prev => (offset === 0 ? page : [...prev, ...page]));
      setHasMore(page.length === PAGE_SIZE);
    } catch (err: any) {
      if (err.name !== "AbortError") setError(err.message);
    } finally {
      setLoading(false);
      setLoadingMore(false);
    }
  };

  useEffect(() => {
    fetchJobs();
    return () => abortRef.current?.abort();
  }, []);

  const handleSearch = (e: FormEvent) => {
    e.preventDefault();
    fetchJobs(search, 0);
  };

  const handleLoadMore = () => {
    fetchJobs(search, jobs.length);
  };

  const triggerIngestion = async () => {
    setIngesting(true);
    setStats(null);
    try {
      const res = await fetch(`${BACKEND_URL}/jobs/ingest`, { method: "POST" });
      if (!res.ok) throw new Error("Ingestion failed");
      const data = await res.json();
      setStats(data);
      // Refresh jobs list after ingestion
      fetchJobs(search, 0);
    } catch (err: any) {
      alert("Error triggering ingestion: " + err.message);
    } finally {
      setIngesting(false);
    }
  };

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <h2>Job Search</h2>
        <button className={styles.ingestBtn} onClick={triggerIngestion} disabled={ingesting}>
          {ingesting ? "Syncing..." : "Sync Jobs Now"}
        </button>
      </div>

      {stats && (
        <div className={styles.stats}>
          <p>Sync complete. Fetched: {stats.fetched}, Inserted: {stats.inserted}, Updated: {stats.updated}, Expired: {stats.expired}</p>
        </div>
      )}

      <form className={styles.searchForm} onSubmit={handleSearch}>
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search by job title..."
          className={styles.searchInput}
        />
        <button type="submit" className={styles.searchBtn}>Search</button>
      </form>

      {loading ? (
        <div className={styles.loading}>Loading jobs...</div>
      ) : error ? (
        <div className={styles.error}>{error}</div>
      ) : (
        <>
          <div className={styles.jobList}>
            {jobs.length === 0 ? (
              <p className={styles.noJobs}>No jobs found. Try syncing or change your search query.</p>
            ) : (
              jobs.map(job => (
                <div
                  key={job.id}
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
                  <h3 className={styles.jobTitle}>{job.title}</h3>
                  <p className={styles.jobCompany}>{job.company} • {job.location || "Remote"}</p>
                  <div className={styles.jobTags}>
                    <span className={styles.tag}>{job.employment_type || "Full-time"}</span>
                    {job.provider && <span className={styles.tagProvider}>via {job.provider}</span>}
                  </div>
                  {job.description && (
                    <p className={styles.jobDescription}>
                      {summarizeJobDescription(job.description, 150)}
                    </p>
                  )}
                  {/* Nested controls stop propagation so they never also fire
                      the card's own "open details" handler. */}
                  <div className={styles.jobActions} onClick={(e) => e.stopPropagation()}>
                    <button
                      type="button"
                      className={styles.detailsBtn}
                      onClick={() => setSelectedJob(job)}
                    >
                      View Details
                    </button>
                    {(job.url || job.raw_payload?.url) && (
                      <a href={job.url || job.raw_payload?.url} target="_blank" rel="noopener noreferrer" className={styles.applyBtn}>
                        View & Apply
                      </a>
                    )}
                  </div>
                </div>
              ))
            )}
          </div>

          {hasMore && (
            <button
              type="button"
              className={styles.loadMoreBtn}
              onClick={handleLoadMore}
              disabled={loadingMore}
            >
              {loadingMore ? "Loading..." : "Load more"}
            </button>
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
