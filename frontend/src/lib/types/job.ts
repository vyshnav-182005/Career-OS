export interface JobFeatureScores {
  semantic: number;
  skill_overlap: number;
  family_fit: number;
  seniority_fit: number;
  recency: number;
}

export type JobMatchVerdict = "strong" | "possible" | "reject";

/**
 * "analyzed" — the real LLM-backed ATS score from a completed fit analysis.
 * "estimated" — the deterministic estimate the backend computes for every card
 * so the list can show a percentage without an LLM call per job.
 */
export type AtsScoreSource = "analyzed" | "estimated";

export interface Job {
  id: string;
  title: string;
  company: string;
  location: string | null;
  description: string | null;
  skills?: string[];
  employment_type: string | null;
  salary: string | null;
  posted_date: string | null;
  provider: string;
  provider_job_id: string;
  raw_payload?: any;
  similarity?: number;
  url?: string;

  // Job Matching Agent output (Phase 3) — optional so a legacy/unranked
  // response (missing verdict/score/etc) still renders correctly.
  verdict?: JobMatchVerdict;
  score?: number;
  reason?: string;
  matched_skills?: string[];
  missing_skills?: string[];
  feature_scores?: JobFeatureScores;

  // Resume ATS match shown on the job card (0–100).
  ats_match_score?: number;
  ats_score_source?: AtsScoreSource;
}

/**
 * The recommendation endpoint returns two different shapes depending on path:
 *  - legacy (?legacy=true / embedding-fallback): a flat MatchedJob-like row.
 *  - the Phase 2/3 default path: { job: {...}, features, verdict, score,
 *    reason, matched_skills, missing_skills, retrieval_sources,
 *    ats_match_score, ats_score_source }.
 * This normalizes either into a single flat `Job` the UI can render.
 */
interface RankedJobEntry {
  job: Job;
  verdict?: JobMatchVerdict;
  score?: number;
  reason?: string;
  matched_skills?: string[];
  missing_skills?: string[];
  features?: JobFeatureScores;
  ats_match_score?: number;
  ats_score_source?: AtsScoreSource;
}

export function normalizeRecommendedJob(entry: unknown): Job {
  if (entry && typeof entry === "object" && "job" in entry) {
    const ranked = entry as RankedJobEntry;
    return {
      ...ranked.job,
      verdict: ranked.verdict,
      score: ranked.score,
      reason: ranked.reason,
      matched_skills: ranked.matched_skills,
      missing_skills: ranked.missing_skills,
      feature_scores: ranked.features,
      ats_match_score: ranked.ats_match_score,
      ats_score_source: ranked.ats_score_source,
    };
  }
  return entry as Job;
}

/**
 * The percentage a job card shows. Prefers the backend's ATS match score and
 * falls back to the raw embedding similarity of a legacy/unranked row, so a
 * card is never left without a number when one is derivable.
 */
export function jobMatchPercent(job: Job): number | null {
  if (typeof job.ats_match_score === "number" && Number.isFinite(job.ats_match_score)) {
    return Math.max(0, Math.min(100, Math.round(job.ats_match_score)));
  }
  if (typeof job.similarity === "number" && Number.isFinite(job.similarity)) {
    return Math.max(0, Math.min(100, Math.round(job.similarity * 100)));
  }
  return null;
}
