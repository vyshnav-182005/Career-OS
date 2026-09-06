-- Caps the description's contribution to jobs.search_vector.
--
-- The trigger indexed the entire description at weight C. That was fine when
-- jobs came from a keyword aggregator whose "description" was a ~300 character
-- snippet. The ATS board providers (Greenhouse, Lever) return the *full* JD -
-- 6.6kB on average - so the tsvector grew to 5.3kB per row, 47MB across the
-- table, and every one of them was TOASTed out of line.
--
-- search_jobs_fulltext ranks with ts_rank(search_vector, query), which has to
-- read each matching tsvector back in. Measured on 9.3k rows with ~2k matches:
-- 4.0s for the query, and before ANALYZE refreshed the planner's stats it was
-- picking a sequential scan and taking 31s - past the statement timeout, so the
-- RPC raised, the caller swallowed it, and the lexical leg of hybrid retrieval
-- silently returned nothing at all.
--
-- Truncating the description to the first 2000 characters takes the average
-- tsvector from 3.7kB to 1.5kB, which puts most rows back under the TOAST
-- threshold and keeps them inline.
--
-- The tradeoff: a term that appears ONLY past ~2000 characters of a JD no
-- longer matches lexically. Title (weight A) and the skills array (weight B)
-- are indexed in full and unaffected, and the semantic leg still sees the
-- description via the job embedding, so this costs recall only on a keyword
-- buried deep in a long posting and mentioned nowhere else.
--
-- Run this in Supabase Dashboard -> SQL Editor.

CREATE OR REPLACE FUNCTION public.jobs_search_vector_update()
RETURNS trigger
LANGUAGE plpgsql
AS $function$
BEGIN
  NEW.search_vector :=
    setweight(to_tsvector('english', coalesce(NEW.title, '')), 'A') ||
    setweight(to_tsvector('english', array_to_string(coalesce(NEW.skills, '{}'::text[]), ' ')), 'B') ||
    -- Capped: see the header. Keep this in step with any change to how much
    -- description the providers store.
    setweight(to_tsvector('english', left(coalesce(NEW.description, ''), 2000)), 'C');
  RETURN NEW;
END;
$function$;

-- Rebuild the existing rows through the new definition.
UPDATE public.jobs
SET search_vector =
    setweight(to_tsvector('english', coalesce(title, '')), 'A') ||
    setweight(to_tsvector('english', array_to_string(coalesce(skills, '{}'::text[]), ' ')), 'B') ||
    setweight(to_tsvector('english', left(coalesce(description, ''), 2000)), 'C');

-- The planner needs current statistics to keep choosing the GIN index over a
-- sequential scan here; without this it was costing the seq scan too cheaply.
ANALYZE public.jobs;
