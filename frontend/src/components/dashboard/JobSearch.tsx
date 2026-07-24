"use client";

import { useState, useEffect, FormEvent } from "react";
import styles from "./JobSearch.module.css";

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
}

export default function JobSearch() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [ingesting, setIngesting] = useState(false);
  const [stats, setStats] = useState<any>(null);

  const fetchJobs = async (query = "") => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`http://localhost:8000/jobs${query ? `?title=${encodeURIComponent(query)}` : ''}`);
      if (!res.ok) throw new Error("Failed to fetch jobs");
      const data = await res.json();
      setJobs(data.data || []);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchJobs();
  }, []);

  const handleSearch = (e: FormEvent) => {
    e.preventDefault();
    fetchJobs(search);
  };

  const triggerIngestion = async () => {
    setIngesting(true);
    setStats(null);
    try {
      const res = await fetch("http://localhost:8000/jobs/ingest", { method: "POST" });
      if (!res.ok) throw new Error("Ingestion failed");
      const data = await res.json();
      setStats(data);
      // Refresh jobs list after ingestion
      fetchJobs(search);
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
        <div className={styles.jobList}>
          {jobs.length === 0 ? (
            <p className={styles.noJobs}>No jobs found. Try syncing or change your search query.</p>
          ) : (
            jobs.map(job => (
              <div key={job.id} className={styles.jobCard}>
                <h3 className={styles.jobTitle}>{job.title}</h3>
                <p className={styles.jobCompany}>{job.company} • {job.location || "Remote"}</p>
                <div className={styles.jobTags}>
                  <span className={styles.tag}>{job.employment_type || "Full-time"}</span>
                  {job.provider && <span className={styles.tagProvider}>via {job.provider}</span>}
                </div>
                {job.description && (
                  <p className={styles.jobDescription}>
                    {job.description.substring(0, 150)}{job.description.length > 150 ? "..." : ""}
                  </p>
                )}
                {job.raw_payload?.url && (
                  <a href={job.raw_payload.url} target="_blank" rel="noopener noreferrer" className={styles.applyBtn}>
                    View & Apply
                  </a>
                )}
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}
