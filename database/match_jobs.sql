-- Add URL column to the jobs table if it doesn't exist
ALTER TABLE public.jobs ADD COLUMN IF NOT EXISTS url TEXT;

-- Function to match jobs based on profile embedding
CREATE OR REPLACE FUNCTION match_jobs (
  query_embedding vector(384),
    match_threshold float,
      match_count int
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
                                                                                                                          WHERE 1 - (j.embedding <=> query_embedding) > match_threshold
                                                                                                                              AND j.status = 'ACTIVE'
                                                                                                                                ORDER BY j.embedding <=> query_embedding
                                                                                                                                  LIMIT match_count;
                                                                                                                                  END;
                                                                                                                                  $$;
                                                                                                                                  