-- Enable the pgvector extension to work with embeddings
CREATE EXTENSION IF NOT EXISTS vector;

-- Create the jobs table
CREATE TABLE IF NOT EXISTS public.jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        provider TEXT NOT NULL,
            provider_job_id TEXT NOT NULL,
                title TEXT NOT NULL,
                    company TEXT NOT NULL,
                        location TEXT,
                            description TEXT,
                                skills TEXT[] DEFAULT '{}',
                                    employment_type TEXT,
                                        salary TEXT,
                                            posted_date TIMESTAMPTZ,
                                                raw_payload JSONB,
                                                    embedding vector(384),
                                                        status TEXT DEFAULT 'ACTIVE',
                                                            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                                                                updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                                                                    UNIQUE(provider, provider_job_id)
                                                                    );

                                                                    -- Enable Row Level Security (optional but recommended)
                                                                    ALTER TABLE public.jobs ENABLE ROW LEVEL SECURITY;

                                                                    -- Allow public read access (or restrict to authenticated users)
                                                                    CREATE POLICY "Jobs are readable by everyone" 
                                                                    ON public.jobs FOR SELECT 
                                                                    USING (true);

                                                                    -- Allow service role full access (for your backend ingestion)
                                                                    CREATE POLICY "Service role has full access to jobs" 
                                                                    ON public.jobs FOR ALL 
                                                                    USING (auth.role() = 'service_role');
                                                                    