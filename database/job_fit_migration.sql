-- Job-specific optimized project bullets + ATS scoring persistence.
-- Run this in Supabase Dashboard -> SQL Editor (after performance_indexes.sql).

CREATE TABLE IF NOT EXISTS public.job_resume_optimizations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    job_id UUID NOT NULL REFERENCES public.jobs(id) ON DELETE CASCADE,
    optimized_resume_json JSONB,
    optimized_projects JSONB NOT NULL DEFAULT '[]'::jsonb,
    ats_score JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, job_id)
);

CREATE INDEX IF NOT EXISTS idx_job_resume_optimizations_lookup
    ON public.job_resume_optimizations (user_id, job_id);

-- Reuses the update_updated_at() trigger function created in supabase_migration.sql
CREATE TRIGGER job_resume_optimizations_updated_at
    BEFORE UPDATE ON public.job_resume_optimizations
    FOR EACH ROW
    EXECUTE FUNCTION public.update_updated_at();

ALTER TABLE public.job_resume_optimizations ENABLE ROW LEVEL SECURITY;

-- Matches the jobs/profiles convention: backend uses the service-role key only,
-- per-user scoping is enforced at the application layer (internal-secret + session proxy).
CREATE POLICY "Service role full access on job_resume_optimizations"
    ON public.job_resume_optimizations
    FOR ALL
    USING (true)
    WITH CHECK (true);
