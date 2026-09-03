-- Performance indexes for job lookup + cached profile embeddings.
-- Run this in Supabase Dashboard -> SQL Editor.

-- Trigram search support for ilike '%term%' filters on title/company
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE INDEX IF NOT EXISTS idx_jobs_title_trgm ON public.jobs USING gin (title gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_jobs_company_trgm ON public.jobs USING gin (company gin_trgm_ops);

-- Every job query filters on status and orders by posted_date
CREATE INDEX IF NOT EXISTS idx_jobs_status_posted ON public.jobs (status, posted_date DESC);

-- match_jobs() does a cosine-distance scan over embedding with no index today.
-- HNSW needs no list-count tuning (unlike ivfflat) and works well from small to large tables.
CREATE INDEX IF NOT EXISTS idx_jobs_embedding_hnsw
  ON public.jobs USING hnsw (embedding vector_cosine_ops);

-- Cache the profile embedding so /jobs/recommended doesn't recompute it on every request.
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS profile_embedding vector(384);
