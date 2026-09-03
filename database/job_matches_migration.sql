-- Job Matching Agent cache (Phase 3 of the job-matching rework).
-- Run this in Supabase Dashboard -> SQL Editor
-- (after job_matching_migration.sql and hybrid_search_migration.sql).
-- Idempotent: safe to re-run.

-- Cache key for job_matches: invalidated whenever profile_data changes.
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS profile_version TEXT;

CREATE TABLE IF NOT EXISTS public.job_matches (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    job_id UUID NOT NULL REFERENCES public.jobs(id) ON DELETE CASCADE,
    verdict TEXT NOT NULL,
    score NUMERIC NOT NULL,
    reason TEXT,
    matched_skills JSONB NOT NULL DEFAULT '[]'::jsonb,
    missing_skills JSONB NOT NULL DEFAULT '[]'::jsonb,
    profile_version TEXT,
    feature_scores JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, job_id)
);

CREATE INDEX IF NOT EXISTS idx_job_matches_user_score
    ON public.job_matches (user_id, score DESC);

-- Reuses the update_updated_at() trigger function created in supabase_migration.sql
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_trigger WHERE tgname = 'job_matches_updated_at'
  ) THEN
    CREATE TRIGGER job_matches_updated_at
      BEFORE UPDATE ON public.job_matches
      FOR EACH ROW
      EXECUTE FUNCTION public.update_updated_at();
  END IF;
END $$;

ALTER TABLE public.job_matches ENABLE ROW LEVEL SECURITY;

-- Matches the jobs/profiles convention: backend uses the service-role key only,
-- per-user scoping is enforced at the application layer (internal-secret + session proxy).
DROP POLICY IF EXISTS "Service role full access on job_matches" ON public.job_matches;
CREATE POLICY "Service role full access on job_matches"
    ON public.job_matches
    FOR ALL
    USING (true)
    WITH CHECK (true);
