-- job_matches.from_llm: distinguishes a real LLM verdict from the feature-ranking
-- fallback written when the LLM call failed, timed out, or came back malformed.
--
-- Why the column exists. The cache is keyed on profile_version, which only
-- changes when the user's profile does. Persisting a fallback under that key
-- pinned "the AI reviewer was unavailable" to a job until the next profile
-- edit, long outliving the outage that caused it. The fix for that was to stop
-- persisting fallbacks at all - which traded a stale-result bug for a latency
-- one: with nothing cached, every page load re-fired the whole LLM fan-out for
-- those jobs, so a provider having a bad minute made the Jobs page slow for as
-- long as it lasted.
--
-- Marking the row instead lets the reader treat the two kinds differently: a
-- real verdict stays cached until the profile changes, a fallback is served
-- only briefly (see FALLBACK_CACHE_TTL_SECONDS in db/supabase_client.py) and
-- then retried. Repeat loads stay fast; a fallback still heals on its own.
--
-- Existing rows default to true. Before this column existed only real verdicts
-- were persisted, so that is the correct reading of the history.

ALTER TABLE public.job_matches
    ADD COLUMN IF NOT EXISTS from_llm boolean NOT NULL DEFAULT true;

-- The read path filters on (user_id, profile_version) and then needs updated_at
-- to age out fallbacks; keeping from_llm/updated_at in the index lets that stay
-- an index-only decision.
CREATE INDEX IF NOT EXISTS idx_job_matches_user_version
    ON public.job_matches (user_id, profile_version)
    INCLUDE (from_llm, updated_at);
