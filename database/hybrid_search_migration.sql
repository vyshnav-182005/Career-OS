-- Hybrid retrieval support (Phase 2 of the job-matching rework).
-- Run this in Supabase Dashboard -> SQL Editor, after job_matching_migration.sql.
-- Idempotent: safe to re-run. Does not touch match_jobs (v1) - it stays in
-- place unmodified so /jobs/recommended?legacy=true can roll back to it.

-- 1. Full-text search column + index -----------------------------------
-- Not a GENERATED column: to_tsvector() is STABLE, not IMMUTABLE (the active
-- text search config can change via ALTER TEXT SEARCH CONFIGURATION), and
-- Postgres rejects STABLE expressions in GENERATED ALWAYS AS with 42P17.
-- A trigger-maintained column is the standard workaround.

ALTER TABLE public.jobs ADD COLUMN IF NOT EXISTS search_vector tsvector;

CREATE OR REPLACE FUNCTION public.jobs_search_vector_update() RETURNS trigger AS $$
BEGIN
  NEW.search_vector :=
    setweight(to_tsvector('english', coalesce(NEW.title, '')), 'A') ||
    setweight(to_tsvector('english', array_to_string(coalesce(NEW.skills, '{}'::text[]), ' ')), 'B') ||
    setweight(to_tsvector('english', coalesce(NEW.description, '')), 'C');
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS jobs_search_vector_trigger ON public.jobs;
CREATE TRIGGER jobs_search_vector_trigger
  BEFORE INSERT OR UPDATE ON public.jobs
  FOR EACH ROW
  EXECUTE FUNCTION public.jobs_search_vector_update();

-- Backfill rows that existed before the trigger did.
UPDATE public.jobs SET search_vector =
    setweight(to_tsvector('english', coalesce(title, '')), 'A') ||
    setweight(to_tsvector('english', array_to_string(coalesce(skills, '{}'::text[]), ' ')), 'B') ||
    setweight(to_tsvector('english', coalesce(description, '')), 'C')
  WHERE search_vector IS NULL;

CREATE INDEX IF NOT EXISTS idx_jobs_search_vector ON public.jobs USING GIN (search_vector);

-- 2. match_jobs_v2 - vector retrieval with hard family/date/location gates --
-- Same similarity ranking as match_jobs, but role_family/excluded_families/
-- min_posted_date/locations are SQL predicates, not post-filters, so an
-- excluded or off-target family is unreachable regardless of similarity.
-- must_have_skills here is a soft prefilter (array overlap); the hard,
-- alias-canonicalized skill gate happens in Python (job_matching.py).

CREATE OR REPLACE FUNCTION match_jobs_v2 (
  query_embedding vector(384),
  target_families text[] DEFAULT '{}',
  excluded_families text[] DEFAULT '{}',
  must_have_skills text[] DEFAULT '{}',
  min_posted_date timestamptz DEFAULT NULL,
  locations text[] DEFAULT '{}',
  match_threshold float DEFAULT 0.0,
  match_count int DEFAULT 60
)
RETURNS TABLE (
  id uuid,
  provider text,
  provider_job_id text,
  title text,
  company text,
  location text,
  description text,
  skills text[],
  employment_type text,
  salary text,
  posted_date timestamptz,
  url text,
  raw_payload jsonb,
  status text,
  created_at timestamptz,
  updated_at timestamptz,
  role_family text,
  similarity float
)
LANGUAGE plpgsql
AS $$
BEGIN
  RETURN QUERY
  SELECT
    j.id,
    j.provider,
    j.provider_job_id,
    j.title,
    j.company,
    j.location,
    j.description,
    j.skills,
    j.employment_type,
    j.salary,
    j.posted_date,
    j.url,
    j.raw_payload,
    j.status,
    j.created_at,
    j.updated_at,
    j.role_family,
    1 - (j.embedding <=> query_embedding) AS similarity
  FROM jobs j
  WHERE j.status = 'ACTIVE'
    -- role_family IS NULL must pass this gate. In SQL, NULL = ANY(...) is NULL
    -- rather than false, so without the explicit test every job we could not
    -- classify is silently invisible to any candidate with a search intent -
    -- which was 69% of the table, including most security and hardware roles.
    -- Unclassified jobs are NOT waved through unscored: _family_fit() in
    -- services/job_matching.py gives them 0.4 (against 1.0 for an exact family
    -- match), so they rank below classified work and still face MIN_SCORE and
    -- the LLM verdict. Note the excluded_families line below already spelled
    -- this out; this is the same rule applied to the positive gate.
    AND (cardinality(target_families) = 0 OR j.role_family IS NULL OR j.role_family = ANY(target_families))
    AND (cardinality(excluded_families) = 0 OR j.role_family IS NULL OR j.role_family <> ALL(excluded_families))
    AND (min_posted_date IS NULL OR j.posted_date >= min_posted_date)
    AND (
      cardinality(locations) = 0
      OR EXISTS (SELECT 1 FROM unnest(locations) AS loc WHERE j.location ILIKE '%' || loc || '%')
    )
    AND (cardinality(must_have_skills) = 0 OR j.skills && must_have_skills)
    AND 1 - (j.embedding <=> query_embedding) > match_threshold
  ORDER BY j.embedding <=> query_embedding
  LIMIT match_count;
END;
$$;

-- 3. search_jobs_fulltext - lexical retrieval leg for the RRF fusion --------

CREATE OR REPLACE FUNCTION search_jobs_fulltext (
  search_query text,
  target_families text[] DEFAULT '{}',
  match_count int DEFAULT 60
)
RETURNS TABLE (
  id uuid,
  provider text,
  provider_job_id text,
  title text,
  company text,
  location text,
  description text,
  skills text[],
  employment_type text,
  salary text,
  posted_date timestamptz,
  url text,
  raw_payload jsonb,
  status text,
  created_at timestamptz,
  updated_at timestamptz,
  role_family text,
  rank float
)
LANGUAGE plpgsql
AS $$
BEGIN
  RETURN QUERY
  SELECT
    j.id,
    j.provider,
    j.provider_job_id,
    j.title,
    j.company,
    j.location,
    j.description,
    j.skills,
    j.employment_type,
    j.salary,
    j.posted_date,
    j.url,
    j.raw_payload,
    j.status,
    j.created_at,
    j.updated_at,
    j.role_family,
    -- ts_rank() returns real (float4); the RETURNS TABLE column below is
    -- float8, and RETURN QUERY requires an exact type match, not just an
    -- implicit cast - without this cast every call fails with 42804.
    ts_rank(j.search_vector, websearch_to_tsquery('english', search_query))::double precision AS rank
  FROM jobs j
  WHERE j.status = 'ACTIVE'
    AND j.search_vector @@ websearch_to_tsquery('english', search_query)
    -- role_family IS NULL must pass this gate. In SQL, NULL = ANY(...) is NULL
    -- rather than false, so without the explicit test every job we could not
    -- classify is silently invisible to any candidate with a search intent -
    -- which was 69% of the table, including most security and hardware roles.
    -- Unclassified jobs are NOT waved through unscored: _family_fit() in
    -- services/job_matching.py gives them 0.4 (against 1.0 for an exact family
    -- match), so they rank below classified work and still face MIN_SCORE and
    -- the LLM verdict. match_jobs_v2 gates the same way.
    AND (cardinality(target_families) = 0 OR j.role_family IS NULL OR j.role_family = ANY(target_families))
  ORDER BY rank DESC
  LIMIT match_count;
END;
$$;
