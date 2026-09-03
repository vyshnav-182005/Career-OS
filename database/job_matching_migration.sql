-- Job matching taxonomy columns (Phase 1 of the job-matching rework).
-- Run this in Supabase Dashboard -> SQL Editor.
-- Idempotent: safe to re-run.

ALTER TABLE public.jobs ADD COLUMN IF NOT EXISTS role_family TEXT;
ALTER TABLE public.jobs ADD COLUMN IF NOT EXISTS source_query TEXT;
ALTER TABLE public.jobs ADD COLUMN IF NOT EXISTS last_seen_at TIMESTAMPTZ DEFAULT now();
ALTER TABLE public.jobs ADD COLUMN IF NOT EXISTS content_hash TEXT;

-- match_jobs_v2 (Phase 2) will filter on (status, role_family) together.
CREATE INDEX IF NOT EXISTS idx_jobs_status_role_family ON public.jobs (status, role_family);

-- Supports expiring/prioritising by freshness once role_family filtering lands.
CREATE INDEX IF NOT EXISTS idx_jobs_last_seen_at ON public.jobs (last_seen_at);
