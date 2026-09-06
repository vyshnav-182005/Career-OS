"use client";

import { useCallback, useEffect, useRef, useState, FormEvent } from "react";
import type { Job } from "@/lib/types/job";
import { normalizeRecommendedJob, jobMatchPercent } from "@/lib/types/job";
import JobDetailModal from "./JobDetailModal";
import styles from "./JobsBoard.module.css";

interface JobsBoardProps {
  hasProfile: boolean;
  cacheScope: string;
}

/** Profile matches shown when the search box is empty. */
const TOP_MATCHES_LIMIT = 10;
/** Results shown for a search. */
const SEARCH_LIMIT = 20;
/** Debounce before a keystroke becomes a request. */
const SEARCH_DEBOUNCE_MS = 400;
/**
 * How long to wait before re-checking after the backend reports it is sourcing.
 * Ingestion runs as a background task once the response has been sent, so the
 * jobs a first-time user in a new field is waiting for land shortly after their
 * empty page does. One automatic retry turns that into "the list fills itself
 * in" instead of "reload and hope".
 */
const SOURCING_RETRY_MS = 12_000;

/**
 * The proxy answers 503 only when it could not reach the backend at all (see
 * lib/backendFetch.ts) - never for a backend that answered with an error. In
 * development both processes start from one command and the backend needs
 * ~10s of imports before it binds its port, so a 503 on the first load is
 * overwhelmingly "not up yet" rather than "broken".
 *
 * Retrying here rather than making the proxy sit on a long connect loop is
 * what keeps the page quick: the request returns immediately, the user gets a
 * "starting up" message instead of a frozen spinner or an error they have to
 * reload out of, and the cards appear the moment the backend answers. The
 * delays ramp so a backend that really is down settles down rather than being
 * hammered, and stop after ~25s, at which point it is reported as an error.
 */
const BACKEND_UNREACHABLE_STATUS = 503;
const STARTUP_RETRY_DELAYS_MS = [400, 800, 1500, 2500, 4000, 5000, 5000, 5000];

type Mode = "recommended" | "search";

interface JobCacheEntry {
  jobs: Job[];
  mode: Mode;
  activeQuery: string;
  sourcing: boolean;
  createdAt: number;
}

const JOB_CACHE_TTL_MS = 15 * 60 * 1000;
const JOB_CACHE_PREFIX = "career-os:jobs:";
const memoryJobCache = new Map<string, JobCacheEntry>();

function cacheKeyFor(cacheScope: string, searchTerm: string): string {
  const trimmed = searchTerm.trim();
  const mode: Mode = trimmed ? "search" : "recommended";
  return `${cacheScope}:${mode}:${trimmed.toLowerCase()}`;
}

async function errorMessageFor(response: Response, fallback: string): Promise<string> {
  try {
    const data: unknown = await response.json();
    if (data && typeof data === "object") {
      const detail = "detail" in data ? data.detail : undefined;
      const error = "error" in data ? data.error : undefined;
      const message = "message" in data ? data.message : undefined;

      if (typeof detail === "string") return detail;
      if (typeof error === "string") return error;
      if (typeof message === "string") return message;
    }
  } catch {
    // Some proxy/backend failures are plain text or empty; fall through.
  }

  return fallback;
}

function getCachedJobs(cacheKey: string): JobCacheEntry | null {
  const memoryEntry = memoryJobCache.get(cacheKey);
  if (memoryEntry && Date.now() - memoryEntry.createdAt < JOB_CACHE_TTL_MS) {
    return memoryEntry;
  }

  memoryJobCache.delete(cacheKey);

  try {
    const serialized = window.sessionStorage.getItem(`${JOB_CACHE_PREFIX}${cacheKey}`);
    if (!serialized) return null;

    const entry = JSON.parse(serialized) as JobCacheEntry;
    if (!entry.createdAt || Date.now() - entry.createdAt >= JOB_CACHE_TTL_MS) {
      window.sessionStorage.removeItem(`${JOB_CACHE_PREFIX}${cacheKey}`);
      return null;
    }

    memoryJobCache.set(cacheKey, entry);
    return entry;
  } catch {
    return null;
  }
}

function setCachedJobs(cacheKey: string, entry: JobCacheEntry) {
  memoryJobCache.set(cacheKey, entry);

  try {
    window.sessionStorage.setItem(`${JOB_CACHE_PREFIX}${cacheKey}`, JSON.stringify(entry));
  } catch {
    // Storage can be unavailable or full; the in-memory cache still covers tab switches.
  }
}

function scoreTier(score: number): "good" | "fair" | "poor" {
  if (score >= 75) return "good";
  if (score >= 50) return "fair";
  return "poor";
}

function applyUrlFor(job: Job): string | undefined {
  return (
    job.url ||
    job.raw_payload?.redirect_url ||
    job.raw_payload?.url ||
    job.raw_payload?.link ||
    undefined
  );
}

export default function JobsBoard({ hasProfile, cacheScope }: JobsBoardProps) {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [mode, setMode] = useState<Mode>("recommended");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedJob, setSelectedJob] = useState<Job | null>(null);
  // Set when the modal was opened by "Optimize Resume" rather than by
  // clicking the card, so generation starts without a second click.
  const [autoGenerate, setAutoGenerate] = useState(false);

  const [query, setQuery] = useState("");
  // The term the currently displayed results belong to, so the empty state can
  // name it without flickering to the in-flight term mid-request.
  const [activeQuery, setActiveQuery] = useState("");
  const [sourcing, setSourcing] = useState(false);
  // True while we are waiting out a backend that hasn't finished starting.
  const [starting, setStarting] = useState(false);

  const abortRef = useRef<AbortController | null>(null);
  // How many startup retries this attempt has already spent, and the pending
  // timer, so a new query or an unmount cancels it.
  const startupAttemptRef = useRef(0);
  const startupTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Lets `load` reschedule itself without being its own dependency.
  const loadRef = useRef<(searchTerm: string) => void>(() => {});

  const load = useCallback(
    async (searchTerm: string) => {
      const trimmed = searchTerm.trim();
      const nextMode: Mode = trimmed ? "search" : "recommended";
      const cacheKey = cacheKeyFor(cacheScope, trimmed);
      const cached = getCachedJobs(cacheKey);

      if (cached) {
        abortRef.current?.abort();
        setJobs(cached.jobs);
        setMode(cached.mode);
        setActiveQuery(cached.activeQuery);
        setSourcing(cached.sourcing);
        setError(null);
        // Cards are on screen, so whatever the backend was doing is moot.
        setStarting(false);
        setLoading(false);
        return;
      }

      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;

      setLoading(true);
      setError(null);
      setSourcing(false);

      try {
        const url = trimmed
          ? `/api/jobs/search?q=${encodeURIComponent(trimmed)}&limit=${SEARCH_LIMIT}`
          : `/api/jobs/recommended?limit=${TOP_MATCHES_LIMIT}`;

        const res = await fetch(url, { signal: controller.signal });

        if (res.status === BACKEND_UNREACHABLE_STATUS) {
          const delay = STARTUP_RETRY_DELAYS_MS[startupAttemptRef.current];
          if (delay !== undefined) {
            startupAttemptRef.current += 1;
            setStarting(true);
            setError(null);
            startupTimerRef.current = setTimeout(() => loadRef.current(searchTerm), delay);
            return;
          }
          // Budget spent - it isn't starting, it's down. Fall through and
          // report it like any other failure.
        }

        if (!res.ok) {
          throw new Error(await errorMessageFor(res, trimmed ? "Failed to search jobs" : "Failed to load your matches"));
        }

        startupAttemptRef.current = 0;
        setStarting(false);

        const data = await res.json();
        const raw: unknown[] = data.data || [];
        const nextJobs = raw.map(normalizeRecommendedJob).slice(0, trimmed ? SEARCH_LIMIT : TOP_MATCHES_LIMIT);
        // For a search, an empty result means nothing is stored for that term
        // yet and the backend has queued a fetch for it. For the recommended
        // list the backend says so itself via `sourcing`, since only it knows
        // whether it just kicked ingestion off for this profile's roles.
        const nextSourcing = trimmed
          ? raw.length === 0
          : Boolean(data.sourcing) && raw.length === 0;

        setJobs(nextJobs);
        setMode(nextMode);
        setActiveQuery(trimmed);
        setSourcing(nextSourcing);

        if (!nextSourcing) {
          setCachedJobs(cacheKey, {
            jobs: nextJobs,
            mode: nextMode,
            activeQuery: trimmed,
            sourcing: nextSourcing,
            createdAt: Date.now(),
          });
        }

        // An empty search means the backend has nothing stored for this role
        // yet. It kicks off ingestion for the term as a background task, so
        // say so rather than showing a bare "no results".
      } catch (err: unknown) {
        if (err instanceof DOMException && err.name === "AbortError") return;
        setStarting(false);
        setError(err instanceof Error ? err.message : "Something went wrong");
      } finally {
        if (abortRef.current === controller) setLoading(false);
      }
    },
    [cacheScope]
  );

  // Keeps the retry timer pointed at the current closure rather than one
  // captured from a stale cacheScope. Declared before the effect that triggers
  // the first load, so it is always assigned by the time anything can fire.
  useEffect(() => {
    loadRef.current = load;
  }, [load]);

  // Initial load + debounced re-load as the query changes. Clearing the box
  // falls straight back to the recommendations. A pending startup retry is
  // dropped here: it belongs to the term the user has just moved off, and the
  // load this schedules will re-establish one if the backend is still down.
  useEffect(() => {
    if (!hasProfile) return;
    if (startupTimerRef.current) clearTimeout(startupTimerRef.current);
    startupAttemptRef.current = 0;
    const timer = setTimeout(() => load(query), query ? SEARCH_DEBOUNCE_MS : 0);
    return () => clearTimeout(timer);
  }, [query, hasProfile, load]);

  // Stop a scheduled startup retry from firing after the board is gone.
  useEffect(
    () => () => {
      if (startupTimerRef.current) clearTimeout(startupTimerRef.current);
    },
    []
  );

  // While the backend reports it is sourcing, check back once after the
  // ingestion it queued has had time to land. Deliberately a single retry per
  // sourcing result rather than a poll: `sourcing` only stays true if the
  // retry also came back empty, and re-running this effect then would spin.
  // `retried` guards against exactly that, so a field with genuinely no
  // postings settles on the empty state instead of polling forever.
  const retried = useRef(false);

  // A new search term deserves its own retry budget. Declared before the
  // effect that reads the ref so the reset is not dependent on effect order.
  useEffect(() => {
    retried.current = false;
  }, [query]);

  useEffect(() => {
    if (!sourcing || loading || retried.current) return;
    retried.current = true;
    const timer = setTimeout(() => load(query), SOURCING_RETRY_MS);
    return () => clearTimeout(timer);
  }, [sourcing, loading, load, query]);

  useEffect(() => () => abortRef.current?.abort(), []);

  function openJob(job: Job, generate = false) {
    setAutoGenerate(generate);
    setSelectedJob(job);
  }

  function handleSubmit(e: FormEvent) {
    // Enter skips the debounce rather than doing anything different.
    e.preventDefault();
    load(query);
  }

  if (!hasProfile) {
    return (
      <div className={styles.container}>
        <div className={styles.emptyState}>
          <div className={styles.emptyIcon}>✨</div>
          <h3>No recommendations yet</h3>
          <p>Upload or update your resume to start seeing personalized matches here.</p>
        </div>
      </div>
    );
  }

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <div className={styles.headerText}>
          <h2>{mode === "search" ? "Search Results" : "Your Top Matches"}</h2>
          <p>
            {mode === "search"
              ? `Jobs matching “${activeQuery}”, scored against your profile`
              : "The 10 roles that best fit your profile"}
          </p>
        </div>

        <form className={styles.searchForm} onSubmit={handleSubmit} role="search">
          <svg
            className={styles.searchIcon}
            width="16" height="16" viewBox="0 0 24 24" fill="none"
            stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
            aria-hidden="true"
          >
            <circle cx="11" cy="11" r="8" />
            <line x1="21" y1="21" x2="16.65" y2="16.65" />
          </svg>
          <input
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search a role — e.g. backend engineer"
            className={styles.searchInput}
            aria-label="Search jobs by role"
          />
          {query && (
            <button
              type="button"
              className={styles.clearBtn}
              onClick={() => setQuery("")}
              aria-label="Clear search and show your top matches"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
                <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
              </svg>
            </button>
          )}
        </form>
      </div>

      {starting ? (
        <div className={styles.loadingState}>
          <div className={styles.spinner} />
          <p>Starting the jobs service — your matches will appear here in a moment.</p>
        </div>
      ) : loading ? (
        <div className={styles.loadingState}>
          <div className={styles.spinner} />
          <p>{mode === "search" ? "Searching..." : "Analyzing profile and sourcing roles..."}</p>
        </div>
      ) : error ? (
        <div className={styles.error}>{error}</div>
      ) : jobs.length === 0 ? (
        <div className={styles.emptyState}>
          <div className={styles.emptyIcon}>🔎</div>
          <h3>
            {sourcing
              ? mode === "search"
                ? "Sourcing that role now"
                : "Sourcing roles for your field"
              : "Nothing here yet"}
          </h3>
          <p>
            {sourcing
              ? mode === "search"
                ? `No stored postings for “${activeQuery}” yet — we've started pulling them from our sources. Try this search again in a moment.`
                : "We're pulling in postings that match your background right now. This page will update on its own in a few seconds."
              : "We haven't found jobs in your target roles yet. We're actively pulling in new postings — check back soon."}
          </p>
        </div>
      ) : (
        <ul className={styles.jobGrid}>
          {jobs.map((job) => {
            const matchPercent = jobMatchPercent(job);
            const isEstimate = job.ats_score_source !== "analyzed";
            const applyUrl = applyUrlFor(job);

            return (
              <li key={job.id || `${job.provider}-${job.provider_job_id}`}>
                <div
                  className={styles.jobCard}
                  role="button"
                  tabIndex={0}
                  aria-label={`View full description for ${job.title} at ${job.company}`}
                  onClick={() => openJob(job)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      openJob(job);
                    }
                  }}
                >
                  <div className={styles.jobIdentity}>
                    <h3 className={styles.jobTitle}>{job.title}</h3>
                    <p className={styles.jobCompany}>{job.company}</p>
                  </div>

                  {matchPercent !== null && (
                    <div
                      className={`${styles.matchScore} ${styles[scoreTier(matchPercent)]}`}
                      title={
                        isEstimate
                          ? "Estimated match against your resume. Open the job for a full analysis."
                          : "Match from your completed resume analysis for this job."
                      }
                    >
                      <span className={styles.matchValue}>
                        {isEstimate ? "~" : ""}
                        {matchPercent}
                        <span className={styles.matchPercentSign}>%</span>
                      </span>
                      <span className={styles.matchLabel}>Match</span>
                    </div>
                  )}

                  {/* Nested controls stop propagation so they never also fire
                      the card's own "open details" handler. */}
                  <div className={styles.jobActions} onClick={(e) => e.stopPropagation()}>
                    <button
                      type="button"
                      className={styles.optimizeBtn}
                      onClick={() => openJob(job, true)}
                    >
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                        <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
                      </svg>
                      Optimize Resume
                    </button>

                    {applyUrl ? (
                      <a
                        href={applyUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                        className={styles.applyBtn}
                      >
                        Apply
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                          <line x1="5" y1="12" x2="19" y2="12" />
                          <polyline points="12 5 19 12 12 19" />
                        </svg>
                      </a>
                    ) : (
                      <button type="button" className={styles.applyBtn} disabled>
                        Link N/A
                      </button>
                    )}
                  </div>
                </div>
              </li>
            );
          })}
        </ul>
      )}

      {selectedJob && (
        <JobDetailModal
          // Keyed by job so switching jobs remounts the modal, resetting its
          // analysis/generation state instead of showing the previous job's.
          key={selectedJob.id}
          job={selectedJob}
          hasProfile={hasProfile}
          autoGenerate={autoGenerate}
          onClose={() => {
            setSelectedJob(null);
            setAutoGenerate(false);
          }}
        />
      )}
    </div>
  );
}
