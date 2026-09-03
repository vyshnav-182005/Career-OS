-- Thumbs up/down feedback on recommended jobs (Phase 4 of the job-matching rework).
-- Run this in Supabase Dashboard -> SQL Editor.
-- Idempotent: safe to re-run.

CREATE TABLE IF NOT EXISTS public.job_feedback (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    job_id UUID NOT NULL REFERENCES public.jobs(id) ON DELETE CASCADE,
    vote TEXT NOT NULL CHECK (vote IN ('up', 'down')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, job_id)
);

CREATE INDEX IF NOT EXISTS idx_job_feedback_user
    ON public.job_feedback (user_id);

-- Reuses the update_updated_at() trigger function created in supabase_migration.sql
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_trigger WHERE tgname = 'job_feedback_updated_at'
  ) THEN
    CREATE TRIGGER job_feedback_updated_at
      BEFORE UPDATE ON public.job_feedback
      FOR EACH ROW
      EXECUTE FUNCTION public.update_updated_at();
  END IF;
END $$;

ALTER TABLE public.job_feedback ENABLE ROW LEVEL SECURITY;

-- Matches the jobs/profiles convention: backend uses the service-role key only,
-- per-user scoping is enforced at the application layer (internal-secret + session proxy).
DROP POLICY IF EXISTS "Service role full access on job_feedback" ON public.job_feedback;
CREATE POLICY "Service role full access on job_feedback"
    ON public.job_feedback
    FOR ALL
    USING (true)
    WITH CHECK (true);
