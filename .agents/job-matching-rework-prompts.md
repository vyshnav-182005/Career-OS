# Job Matching Rework — Claude Code Prompts

Ready-to-paste prompts, one per phase, for rebuilding the Career-OS job recommendation
engine so results actually match the résumé.

**Reference:** the full diagnosis and design doc is at
https://claude.ai/code/artifact/a9d2d81f-c439-4a01-867a-5d19e067d57c

---

## How to use these

1. Run Claude Code from the repo root (`C:\Academics\project\Career-OS`).
2. **One phase per session.** Start a fresh session for each — these are long tasks and
   context from the previous phase mostly gets in the way.
3. Press `shift+tab` twice to enter **plan mode** before pasting. Let Claude produce a plan,
   read it, correct it, then approve. Do not let it start editing from a cold start.
4. **Commit after every phase** on its own branch. If a phase goes wrong you want one
   `git revert`, not an archaeology session.
5. Migrations are applied by hand in the Supabase SQL editor — Claude writes the `.sql`
   file, you run it. Every prompt below says so explicitly.
6. Phases P0 → P4 are ordered by dependency. Do not skip ahead to P3 (the LLM re-ranker);
   it is the most expensive layer and useless while the candidate pool is still polluted.

---

## Phase 0 — Stop the bleeding

*Target: ~4 hours. No schema changes. Removes most of the visible problem.*

```
Context: this is CareerOS, a FastAPI + Next.js career platform. The job recommendation
engine returns badly-matched jobs — DevOps/SRE postings show up for résumés that contain
no infrastructure experience at all. I have diagnosed the causes and want you to fix the
four highest-impact ones. No database schema changes in this phase.

Read these files first before changing anything:
  backend/services/embeddings.py
  backend/services/job_ingestion.py
  backend/routers/jobs.py
  backend/services/scheduler.py
  backend/models/resume.py
  backend/models/profile.py

Then make exactly these changes:

1. FIX THE PROFILE EMBEDDING (backend/services/embeddings.py)
   `generate_profile_embedding` currently reads `original_resume.get("summary")`, but
   ParsedResume has no top-level `summary` — it lives at `personal_info.summary`. So the
   summary is always an empty string. It also ignores skills, experience and projects
   entirely, which is why the query vector is generic.

   Rewrite it to build the embedding text from:
     - personal_info.summary (correct path this time)
     - all skills flattened out of the `skills: list[SkillCategory]` structure
     - every `experience[].title`
     - every technology listed in `projects[].technologies`
     - the inferred `preferred_job_roles[].title` values
     - the `strengths` list

   Critically: format the text to MIRROR the job-side format used by
   `generate_job_embedding` — same "Title: ... Skills: ... Description: ..." shape — so
   both vectors land in the same region of embedding space. Right now the job side is a
   long structured document and the profile side is a short comma-list, which is a large
   part of why similarity collapses toward generic tech.

   Cap the text at a sensible length (all-MiniLM-L6-v2 truncates at 256 word-pieces —
   put titles and skills FIRST so they survive truncation).

2. TURN THE RELEVANCE THRESHOLD BACK ON (backend/routers/jobs.py, ~line 102)
   `match_jobs(profile_embedding, match_threshold=-1.0, match_count=15)` — cosine
   similarity ranges -1 to 1, so -1.0 means every row passes and the function only ranks,
   never filters.

   Introduce a module-level constant `MATCH_THRESHOLD = 0.45` and use it. Also raise
   match_count to 40 so the threshold has room to cut. It is correct and desirable for
   this to return fewer than 15 jobs — do not add any padding or fallback that
   re-introduces low-similarity results when the list comes back short.

3. ALWAYS EMBED ON UPSERT (backend/services/job_ingestion.py, ~lines 51-58)
   The `generate_job_embedding` call currently sits inside the `else` (insert) branch, so
   any job already ACTIVE keeps its old or missing vector forever.

   Move embedding generation OUT of the insert/update branch so it runs for every job.
   Additionally: if `generate_job_embedding` returns None, SKIP that job entirely rather
   than persisting it without an embedding (an unembedded job is invisible to matching
   forever). Count these in IngestionStatistics as `skipped`.

4. CLEAN UP THE INGESTION SOURCES
   - backend/routers/jobs.py: remove `MockJobProvider()` from CONFIGURED_PROVIDERS. Fake
     jobs should never enter the production pool.
   - backend/services/scheduler.py: `run_job_ingestion` calls `workflow.run()` with NO
     query, which makes Jooble return generic high-volume listings that pollute the table
     for everyone. Change it to read the distinct `preferred_job_roles[].title` values
     across all profiles from Supabase and run one targeted ingestion per distinct role
     title. If there are no profiles, log and do nothing — never fall back to an
     unqualified fetch.

Constraints:
- Do not change the database schema or write any migration in this phase.
- Do not touch the frontend in this phase.
- Do not refactor unrelated code, rename modules, or "improve" files you weren't asked
  about. Keep the diff tight and reviewable.
- Preserve existing logging style and the `logger.exception(...)` error handling pattern.

Acceptance criteria — verify before you tell me you're done:
- `python -m pytest tests/ -q` still passes.
- Write a small throwaway script that loads a real profile row from Supabase, builds the
  embedding both the old way and the new way, and prints the resulting text strings.
  Show me both so I can see the difference. Delete the script afterwards.
- Grep the repo to confirm no remaining reference to `match_threshold=-1.0` and no
  remaining `MockJobProvider` import in the router.

Finish by giving me a summary of each change and a `git diff --stat`.
```

---

## Phase 1 — Structured search intent

*Target: 1–2 days. Adds the taxonomy everything downstream filters on.*

```
Context: CareerOS job matching. Phase 0 is done (profile embedding fixed, threshold on).
Now I need to replace free-text role titles with a structured, machine-usable search
intent object, and classify every ingested job into the same taxonomy. This is the
groundwork for hard filtering — no filtering logic yet in this phase.

Read first:
  backend/agents/profile_intelligence_agent.py
  backend/models/profile.py
  backend/models/job.py
  backend/services/job_ingestion.py
  backend/db/supabase_client.py
  database/jobs_migration.sql
  database/supabase_migration.sql

Build these, in this order:

1. THE TAXONOMY (new file: backend/services/taxonomy.py)
   A single source of truth, defined as plain Python constants — no LLM, no network:
     - ROLE_FAMILIES: a fixed list of ~14 slugs. Start with: frontend, backend, fullstack,
       mobile, data-engineering, data-science, ml-engineering, devops-sre, cloud-infra,
       qa-testing, security, embedded, product-design, technical-writing.
     - FAMILY_TITLE_PATTERNS: dict of family -> list of regex/keyword patterns that match
       job titles (e.g. devops-sre matches "devops", "site reliability", "sre",
       "platform engineer", "infrastructure engineer").
     - ADJACENT_FAMILIES: dict of family -> list of families that are a reasonable
       sideways move (frontend <-> fullstack, data-science <-> ml-engineering, and so on).
       devops-sre must NOT be adjacent to frontend, backend, or any application-dev family.
     - SKILL_ALIASES: dict mapping canonical skill -> alias list, so "React", "ReactJS",
       "React.js" all normalise to one token. Cover the ~150 most common tech skills.
     - `canonicalize_skills(raw: list[str]) -> list[str]`
     - `classify_title(title: str) -> str | None` — pattern match first; return None if
       nothing matches confidently rather than guessing.

2. SEARCH INTENT MODEL (backend/models/profile.py)
   Add a `SearchIntent` pydantic model with fields:
     role_families: list[str]          # from ROLE_FAMILIES only
     excluded_families: list[str]      # families this candidate clearly is NOT
     seniority: str                    # intern | junior | mid | senior | lead
     must_have_skills: list[str]       # canonicalised
     nice_to_have_skills: list[str]    # canonicalised
     locations: list[str]
     work_mode: str                    # onsite | hybrid | remote | any
     employment_types: list[str]
   Add `search_intent: SearchIntent | None = None` to `ProfileIntelligence`. Keep it
   Optional so existing profile rows still deserialise.

3. EXTEND THE PROFILE INTELLIGENCE AGENT
   (backend/agents/profile_intelligence_agent.py)
   Extend PROFILE_INTELLIGENCE_PROMPT so the LLM also returns a `search_intent` object.
   Requirements for the prompt:
     - Inject the ROLE_FAMILIES list into the prompt text and instruct the model to pick
       ONLY from that list. Never invent a family slug.
     - Explicitly ask it to populate `excluded_families` — families the résumé shows no
       evidence for. This negative signal is the whole point; say so in the prompt.
     - Derive seniority from total years of experience found in the résumé.
   After parsing the response, VALIDATE server-side: drop any family slug not in
   ROLE_FAMILIES, canonicalise the skill lists through taxonomy.canonicalize_skills, and
   fall back to sensible defaults if the field is missing. Never trust the LLM output shape.

4. JOB COLUMNS + CLASSIFICATION
   - New migration file `database/job_matching_migration.sql` adding to public.jobs:
       role_family TEXT, source_query TEXT, last_seen_at TIMESTAMPTZ DEFAULT now(),
       content_hash TEXT
     plus an index on (status, role_family) and one on last_seen_at.
     Follow the style of database/performance_indexes.sql and make it idempotent
     (IF NOT EXISTS everywhere). I will run it manually in the Supabase SQL editor.
   - Add the matching fields to `NormalizedJob` in backend/models/job.py.
   - In backend/services/job_ingestion.py: set role_family via taxonomy.classify_title,
     set source_query to the query that fetched it, set last_seen_at on every upsert, and
     compute content_hash as a sha256 of title+company+description+skills.
   - Use content_hash to skip re-embedding when a job's content hasn't changed (this is a
     performance win now that Phase 0 embeds on every upsert).

5. BACKFILL SCRIPT (scripts/backfill_job_families.py)
   Standalone script that pages through existing jobs rows, computes role_family and
   content_hash for each, and updates them in batches. Must be safely re-runnable.

Constraints:
- Do NOT add any filtering to match_jobs or the recommendation endpoint yet — that's
  Phase 2. This phase only produces data.
- Do NOT delete or rewrite the existing preferred_job_roles field; search_intent is
  additive and both coexist for now.
- The taxonomy must be deterministic Python. Do not call an LLM to classify job titles at
  ingest time — that's thousands of calls and it will be slow and expensive.

Acceptance criteria:
- `python -m pytest tests/ -q` passes.
- Add `tests/test_taxonomy.py` covering: classify_title on ~20 real job titles including
  ambiguous ones, canonicalize_skills alias collapsing, and that classify_title returns
  None (not a wrong guess) for titles like "Consultant" or "Analyst".
- Show me the generated database/job_matching_migration.sql before I run it.
- Run the profile intelligence agent against one real profile and print the resulting
  search_intent JSON so I can sanity-check the families and exclusions.
```

---

## Phase E — Evaluation harness

*Target: half a day. Build this BEFORE Phase 2 so every later change is measurable.*

```
Context: CareerOS job matching. I'm about to rewrite the retrieval layer and I have no way
to tell whether a change helps — the only current signal is eyeballing job cards. Build me
an offline evaluation harness first.

Read first:
  backend/routers/jobs.py
  backend/db/supabase_client.py
  backend/services/embeddings.py
  backend/services/taxonomy.py

Build:

1. scripts/eval/fixtures/ — a directory holding evaluation résumés as JSON in the
   ParsedResume shape. Generate 6 synthetic but realistic ones spanning clearly distinct
   families: a React frontend developer, a Java backend engineer, a data analyst, an ML
   engineer, a QA automation engineer, and (as a control) an actual DevOps engineer.
   Each should be a plausible 2-4 year-experience résumé with real-sounding skills,
   projects and job titles. Put the expected role_families in a sibling
   `expected.json` keyed by fixture name.

2. scripts/eval/run_eval.py
   For each fixture: build the profile embedding, run the current recommendation path
   (import the real code — do not reimplement it), and dump the top 20 returned jobs to
   `scripts/eval/results/<fixture>_<timestamp>.json` with title, company, similarity and
   role_family.

3. scripts/eval/score.py
   Computes and prints a table of:
     - family_purity@10 — share of the top 10 whose role_family is in the fixture's
       expected families. This is the direct DevOps-contamination metric.
     - cross_family_leak@10 — share of top 10 in a family that is neither expected nor
       adjacent. Should trend to zero.
     - empty_rate — fixtures returning fewer than 3 results.
     - mean_similarity@10
   Plus a `--label` mode that writes a CSV I can open and hand-mark each result
   relevant/not-relevant, and reads that CSV back to compute precision@10.

4. scripts/eval/README.md — how to run it, and a `baseline.md` recording the metrics as
   they stand TODAY, before Phase 2. I want the before/after comparison on record.

Constraints:
- The harness must import the production code paths, never copy them. If the retrieval
  code changes, the harness must automatically exercise the new version.
- It must be read-only against the database — never write, upsert, or delete.
- No LLM calls in the scoring path; these metrics must be deterministic and free to run.

Acceptance criteria:
- `python scripts/eval/run_eval.py && python scripts/eval/score.py` runs end to end and
  prints the metric table.
- Show me baseline.md when you're done. I expect family_purity to be poor — that's the
  number Phase 2 has to move.
```

---

## Phase 2 — Hybrid recall and hard gates

*Target: 2–3 days. This is the structural fix.*

```
Context: CareerOS job matching. Phases 0, 1 and E are done — profile embeddings are fixed,
every job has a role_family, profiles have a structured search_intent, and I have an eval
harness with a recorded baseline. Now replace the single vector-kNN lookup with filtered
hybrid retrieval. This is the change that must make unrelated job families UNREACHABLE
rather than merely unlikely.

Read first:
  database/match_jobs.sql
  database/performance_indexes.sql
  database/job_matching_migration.sql
  backend/routers/jobs.py
  backend/db/supabase_client.py
  backend/services/taxonomy.py
  backend/models/profile.py
  scripts/eval/

Build:

1. FULL-TEXT SEARCH SUPPORT (new migration: database/hybrid_search_migration.sql)
   - Add a generated tsvector column on jobs over title + description, weighted so title
     terms count more (setweight 'A' on title, 'B' on skills, 'C' on description).
   - GIN index on it.
   - Idempotent, in the style of the existing migration files. I will run it manually.

2. NEW RPC: match_jobs_v2 (same migration file or a sibling — your call, but tell me)
   Signature takes: query_embedding vector(384), target_families text[],
   excluded_families text[], must_have_skills text[], min_posted_date timestamptz,
   locations text[], match_threshold float, match_count int.

   It must apply as HARD SQL predicates, not post-filters:
     - status = 'ACTIVE'
     - role_family = ANY(target_families) when target_families is non-empty
     - role_family <> ALL(excluded_families) always
     - posted_date >= min_posted_date
     - similarity > match_threshold
   Return the same columns as match_jobs plus similarity and role_family.
   Keep the old match_jobs function in place — do not drop it — so I can roll back.

3. HYBRID RETRIEVAL SERVICE (new file: backend/services/job_matching.py)
   A `retrieve_candidates(user_id) -> list[ScoredJob]` function that:
     a) Loads search_intent and the cached profile embedding.
     b) Runs THREE retrievers, each returning ~60 candidates:
        - vector: match_jobs_v2 with the profile embedding
        - lexical: a Postgres full-text query built from must_have_skills, with the same
          family predicates applied
        - title-family: direct role_family match ordered by posted_date desc
     c) Fuses the three ranked lists with Reciprocal Rank Fusion (k=60). Implement RRF
        yourself in ~15 lines; do not add a dependency for it.
     d) Scores each survivor on these named, individually-inspectable features:
        - semantic: cosine similarity, normalised 0-1
        - skill_overlap: |canonical résumé skills ∩ canonical job skills| / max(1, |job skills|)
        - family_fit: 1.0 exact family, 0.6 adjacent family (per taxonomy.ADJACENT_FAMILIES),
          0.0 otherwise — and 0.0 is a HARD DROP, not a low score
        - seniority_fit: penalise Senior/Staff/Principal/Lead/Manager titles for junior
          profiles and intern/junior titles for senior profiles
        - recency: linear decay over 45 days
     e) Weighted sum into a final score. Put the weights in a single module-level dict
        with a comment explaining each — I want to tune these by hand.
     f) Applies a MIN_SCORE floor and returns only what clears it.

   Every returned ScoredJob must carry its individual feature scores, not just the total.
   I need to be able to see WHY something ranked where it did.

4. WIRE IT UP (backend/routers/jobs.py)
   `/jobs/recommended` calls the new service. Keep a `?legacy=true` query param that falls
   back to the old path for one release so I can A/B it.

   IMPORTANT: if the result set is small or empty, return it small or empty. Do NOT add a
   fallback that backfills with unfiltered active jobs — that fallback is exactly the bug
   I'm trying to remove. The existing `get_jobs_by_filter` fallback in the embedding-
   failure path should return an empty list with a clear error flag instead.

Constraints:
- Do not add an LLM call anywhere in this phase — that's Phase 3.
- Do not touch the frontend.
- Keep every SQL migration idempotent and show it to me before I run it.
- No new heavy dependencies. Postgres full-text and pgvector are enough.

Acceptance criteria:
- `python -m pytest tests/ -q` passes.
- Add tests/test_job_matching.py covering RRF fusion ordering, the family_fit hard drop,
  skill_overlap arithmetic, and seniority penalties. Use fixtures, not a live database.
- Run scripts/eval/run_eval.py and scripts/eval/score.py and show me the new metric table
  next to baseline.md. family_purity@10 should be at or near 1.0 and cross_family_leak@10
  at 0. If it isn't, tell me why rather than adjusting the metric.
- Show me one full ScoredJob object with its feature breakdown.
```

---

## Phase 3 — The Job Matching Agent

*Target: 2 days. The verification layer the README already promises.*

```
Context: CareerOS job matching. Phase 2 is done — hybrid retrieval with hard family gates
is live and the eval harness shows clean family purity. Now add the final verification
layer: an LLM re-ranker that catches near-misses embeddings and features structurally
cannot distinguish (e.g. a job in the right family that still demands 5 years of a
framework the candidate has never touched).

Note: README.md and Project_Explanation.md already describe a "Job Matching Agent" that
ranks jobs and reports missing skills. It does not exist. This phase builds it.

Read first:
  backend/agents/profile_intelligence_agent.py   (follow its structure and LLM patterns)
  backend/services/job_matching.py
  backend/services/job_fit_analysis.py           (existing per-job analysis — reuse ideas)
  backend/services/job_context.py
  backend/db/supabase_client.py
  backend/models/schemas.py
  database/job_fit_migration.sql                 (follow this migration style)

Build:

1. CACHE TABLE (new migration: database/job_matches_migration.sql)
   public.job_matches with: id, user_id (FK users, cascade), job_id (FK jobs, cascade),
   verdict TEXT, score NUMERIC, reason TEXT, matched_skills JSONB, missing_skills JSONB,
   profile_version TEXT, feature_scores JSONB, created_at, updated_at,
   UNIQUE (user_id, job_id). Index on (user_id, score DESC). RLS + service-role policy
   matching the convention in job_fit_migration.sql. Idempotent. I'll run it manually.

2. PROFILE VERSIONING
   Add a `profile_version` to the profile row — a sha256 of the profile_data JSON,
   computed in backend/db/supabase_client.py when the profile is written. Cached matches
   are invalidated when this changes. Do this cleanly; it's the cache key for everything.

3. THE AGENT (new file: backend/agents/job_matching_agent.py)
   `async def rank_jobs(user_id: str, candidates: list[ScoredJob]) -> list[RankedJob]`
     - Takes the top 25 candidates from Phase 2.
     - Checks the job_matches cache for (user_id, job_id, profile_version) first and only
       sends cache misses to the LLM.
     - ONE batched call for all misses — not one call per job. Send a compact profile
       summary plus a numbered list of jobs (title, company, skills, description truncated
       to ~600 chars each).
     - Returns strict JSON per job: {index, verdict: "strong"|"possible"|"reject",
       score: 0-100, reason: one sentence, matched_skills: [], missing_skills: []}.
     - Use the same NVIDIA NIM client setup, response_format json_object, temperature 0.2,
       and the markdown-fence-stripping + validation pattern from
       profile_intelligence_agent.py.
     - Validate hard: if the response is malformed, or job count doesn't match, log it and
       fall back to the Phase 2 feature ranking rather than returning nothing. The LLM is
       an enhancement, not a hard dependency — a failed call must never break the endpoint.
     - Persist every result to job_matches.

4. WIRE IN
   `/jobs/recommended` becomes: retrieve_candidates() -> rank_jobs() -> drop every
   "reject" -> sort by the agent score -> return top 10. Include reason, matched_skills,
   missing_skills and the Phase 2 feature_scores in the response payload — the frontend
   needs them in Phase 4.

   Because the LLM call adds latency, the endpoint must serve cached matches immediately
   and only block on the LLM for genuinely new jobs. If that would still be slow, return
   the feature-ranked list right away and refresh the LLM ranking in a BackgroundTask —
   follow the existing background-task pattern already in this router.

Constraints:
- One batched LLM call per request maximum. Fan-out per job is not acceptable.
- Never let an LLM failure produce an empty or broken response.
- Do not remove or weaken the Phase 2 hard gates — the agent filters further, never wider.
  A job the retrieval layer excluded must not be reachable through the agent.
- Also update README.md and Project_Explanation.md so the described architecture matches
  what now actually exists.

Acceptance criteria:
- `python -m pytest tests/ -q` passes.
- Add tests/test_job_matching_agent.py with a mocked LLM client covering: cache hit path,
  cache miss path, malformed response fallback, and that "reject" verdicts are dropped.
- Show me a real end-to-end run for one user: the 25 candidates in, and the ranked 10 out
  with reasons. I want to read the reasons and judge whether they're sensible.
- Report the added latency for a cold cache and a warm cache.
```

---

## Phase 4 — Explainable UI and feedback

*Target: 1 day.*

```
Context: CareerOS job matching. The backend now returns, per recommended job, a one-line
reason, matched_skills, missing_skills and a feature-score breakdown. The frontend still
shows only a bare "% Match" badge computed from raw cosine similarity, which tells the
user nothing and tells me nothing when a match is wrong.

Read first:
  frontend/src/components/dashboard/RecommendedJobs.tsx
  frontend/src/components/dashboard/RecommendedJobs.module.css
  frontend/src/components/dashboard/JobDetailModal.tsx
  frontend/src/lib/types/job.ts
  frontend/src/app/api/jobs/recommended/route.ts
  backend/routers/jobs.py

Build:

1. TYPES — extend the `Job` type in frontend/src/lib/types/job.ts with the new fields
   (verdict, score, reason, matched_skills, missing_skills, feature_scores). Make them
   optional so nothing breaks if the backend omits them.

2. JOB CARD (RecommendedJobs.tsx) — replace the raw similarity badge with:
   - a match strength indicator driven by `verdict` (strong / possible), not by raw cosine
   - the one-line `reason` under the title
   - matched_skills as chips in a positive accent
   - missing_skills as chips in a muted/warning style, labelled so it reads as useful
     ("You'd need:") rather than as a rejection
   Follow the existing CSS-module conventions in RecommendedJobs.module.css — do not
   introduce Tailwind, styled-components, or any new styling approach. Match the
   existing dark/light theme token usage.

3. EMPTY STATE — the current empty state says "Upload or update your resume". That's now
   wrong: with real filtering, zero results usually means the job pool has nothing in the
   user's families yet. Write a distinct empty state for "profile exists but no matches
   yet" explaining that we're still sourcing roles, separate from "no profile".

4. FEEDBACK — a thumbs up / thumbs down control on each card. Posts to a new
   `/api/jobs/[id]/feedback` Next.js route that proxies to a new backend endpoint, using
   the same session-derived user_id + X-Internal-Secret pattern as the existing
   recommended route (never trust a client-supplied user_id). Persist to a new
   `job_feedback` table (migration file, idempotent, service-role policy — I'll run it).
   Optimistic UI update; a failed post reverts the control and shows a small inline error.

5. DETAIL MODAL — surface the feature_scores breakdown in JobDetailModal, collapsed
   behind a "Why this match?" disclosure. This is primarily a debugging affordance for me,
   so show the actual numbers, but keep it visually quiet.

Constraints:
- No new frontend dependencies.
- Keep the existing de-duplication and AbortController logic in RecommendedJobs.tsx.
- Accessible: the feedback buttons need aria-labels and visible keyboard focus states.
- Respect prefers-reduced-motion for any transition you add.

Acceptance criteria:
- `npm run dev` starts clean with no TypeScript errors and no console warnings.
- Show me screenshots of a card with a strong match, a card with missing skills, and both
  empty states, in light and dark theme.
```

---

## Phase 5 — Better embedding model (optional)

*Target: half a day plus a backfill. Do this last, and only after the eval harness exists.*

```
Context: CareerOS job matching. All phases done and measured. The last quality lever is the
embedding model itself: all-MiniLM-L6-v2 is trained for symmetric sentence similarity, not
short-query-to-long-document retrieval, which is a poor fit for matching a profile against
a job description.

Swap it for BAAI/bge-small-en-v1.5. This is also 384-dimensional, so NO schema change is
needed — the vector(384) columns and HNSW index stay exactly as they are.

Read first:
  backend/services/embeddings.py
  backend/services/job_ingestion.py
  backend/agents/profile_intelligence_agent.py
  scripts/eval/
  backend/requirements.txt

Do:

1. Update backend/services/embeddings.py to load BAAI/bge-small-en-v1.5. BGE models use an
   asymmetric convention: prefix the QUERY side (the profile) with
   "Represent this sentence for searching relevant passages: " and leave the PASSAGE side
   (the job) unprefixed. Apply this correctly — getting it backwards makes results worse
   than the current model. Normalise embeddings to unit length (BGE expects this for
   cosine similarity).

2. Put the model name in backend/config.py as a setting, defaulting to the new model, so I
   can roll back with an env var and no code change.

3. Write scripts/reembed_all.py — re-embeds every job and every profile with the new model.
   It must be resumable (track progress, safe to Ctrl-C and restart), batched, and log
   throughput. Both sides MUST be re-embedded together — a table with mixed-model vectors
   produces silently garbage similarities, so make the script refuse to run partially and
   say so loudly if interrupted mid-way.

4. Update requirements.txt if needed and note the model download size in the README.

Constraints:
- Do not change the vector dimension, the schema, or the HNSW index.
- Do not change any retrieval logic, weights, or thresholds in this phase — I want to
  measure the model swap in isolation.
- The threshold WILL need retuning afterwards because BGE produces a different similarity
  distribution. Flag this to me with a suggested new value based on the eval run, but do
  not change it yourself.

Acceptance criteria:
- Run scripts/eval/run_eval.py + score.py before and after the re-embed and show me both
  metric tables side by side. If the new model doesn't beat the old one on precision@10
  and family_purity@10, say so plainly and recommend rolling back — a negative result is
  a valid outcome here.
```

---

## After each phase

```
Review the diff you just produced as if you were a senior engineer who did not write it.
Look specifically for: silent exception swallowing, fallbacks that reintroduce unfiltered
results, hardcoded values that should be config, N+1 database calls, and anything that
would break when a profile field is missing. Report what you find — do not fix it yet.
```
