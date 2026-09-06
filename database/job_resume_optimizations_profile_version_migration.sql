-- Adds profile_version to job_resume_optimizations so a cached tailored
-- resume/ATS score is invalidated by an exact profile-content match instead
-- of a timestamp race against profiles.updated_at.
--
-- Why: profiles.updated_at is bumped by the profiles_updated_at trigger on
-- ANY update to the row - including bookkeeping-only writes such as a GitHub
-- sync that only refreshed README-signature cache entries and described no
-- new projects. Comparing job-fit cache freshness against that timestamp
-- meant a routine "Sync with GitHub" click invalidated every job's cached
-- analysis, forcing a full two-LLM-call recompute (ATS scoring, then resume
-- optimization) on the next job opened - even though nothing about the
-- resume itself had changed.
--
-- profile_version (already stored on profiles, computed by
-- backend/db/supabase_client.py::_compute_profile_version) only changes when
-- save_profile_data is called with bump_version=True, i.e. when profile
-- content actually changed. Storing it alongside each cached snapshot and
-- comparing by equality removes the false invalidation entirely.
--
-- Run this in Supabase Dashboard -> SQL Editor.

ALTER TABLE public.job_resume_optimizations
    ADD COLUMN IF NOT EXISTS profile_version TEXT;

CREATE INDEX IF NOT EXISTS idx_job_resume_optimizations_profile_version
    ON public.job_resume_optimizations (profile_version);
