# Phase 0 — Stop the Bleeding (Job Matching Rework)

## Context

CareerOS's job recommendation engine returns badly-matched jobs (e.g. DevOps/SRE postings
for résumés with zero infrastructure experience). The root causes have already been
diagnosed in `.agents/job-matching-rework-prompts.md`. Phase 0 is the first of a
multi-phase rework and targets the four highest-impact, lowest-risk bugs with **no schema
changes** and **no frontend changes**, so the visible symptom stops fast while the deeper
structural work (taxonomy, hybrid retrieval, LLM re-ranking) happens in later phases.

Exploration confirmed all four root causes described in the prompt file are real and
exactly where described:

1. `generate_profile_embedding` reads `profile_data["original_resume"]["summary"]`, but
   `summary` actually lives at `original_resume.personal_info.summary`
   ([resume.py:13](backend/models/resume.py#L13)) — so it's always `""`. The profile text
   format (`"Profile Strengths: ...\nPreferred Roles: ...\nSummary: ..."`) also doesn't
   resemble the job text format (`"Title: ...\nSkills: ...\nDescription: ..."`), so even a
   correct summary wouldn't land the two vectors in the same embedding-space region.
2. `match_jobs(..., match_threshold=-1.0, match_count=15)` at
   [jobs.py:102](backend/routers/jobs.py#L102) disables filtering entirely (cosine
   similarity floor is -1, i.e. every row passes).
3. In [job_ingestion.py:50-60](backend/services/job_ingestion.py#L50-L60), embedding
   generation only happens in the "new job" branch (`else` of the active-id check) — jobs
   that are re-fetched while already `ACTIVE` never get a fresh (or any) embedding.
   `IngestionStatistics.skipped` already exists as a field
   ([job.py:55](backend/models/job.py#L55)) but is never incremented anywhere.
4. `MockJobProvider` is instantiated straight into `CONFIGURED_PROVIDERS` in
   [jobs.py:27-30](backend/routers/jobs.py#L27-L30), feeding fake jobs into the real
   ingestion path. `run_job_ingestion` in
   [scheduler.py:14-26](backend/services/scheduler.py#L14-L26) calls `workflow.run()` with
   no query, which pulls Jooble's generic firehose. There's currently no bulk "all
   profiles" read helper in `backend/db/supabase_client.py` — only per-user lookups
   (`get_profile_data`, `get_cached_profile_embedding`, `get_profile_updated_at`) — so one
   needs to be added.

## Files to change

- `backend/services/embeddings.py`
- `backend/routers/jobs.py`
- `backend/services/job_ingestion.py`
- `backend/services/scheduler.py`
- `backend/db/supabase_client.py` (new helper needed for scheduler change)
- `tests/test_embeddings.py`, `tests/test_job_ingestion.py` (new — no existing tests cover
  this pipeline; closest are `test_job_fit_analysis.py` / `test_ats_scoring.py`)

## 1. Fix the profile embedding (`backend/services/embeddings.py`)

Rewrite `generate_profile_embedding(profile_data: dict)` to build text that mirrors the
job side's `"Title: ...\nSkills: ...\nDescription: ..."` shape, with the highest-signal
fields first so they survive the model's 256-word-piece truncation:

- **Title** — `preferred_job_roles[].title` (from `profile_data["preferred_job_roles"]`,
  same shape `generate_job_embedding`'s caller already expects) joined with the most
  recent `experience[].title` entries from `original_resume.experience`.
- **Skills** — flattened `original_resume.skills` (`list[SkillCategory]` →
  `[s for cat in skills for s in cat.get("skills", [])]`) plus every
  `projects[].technologies`, deduplicated while preserving order.
- **Description** — `strengths` list, followed by
  `original_resume.personal_info.summary` (correct path this time), lowest priority since
  it's most expendable under truncation.

Since `profile_data` here is a raw dict (as read from Supabase JSONB / `model_dump()` of
`ProfileIntelligence`), all field access stays dict-based (`.get(...)`), matching the
existing style — no new Pydantic parsing.

Cap the built text at roughly 200 words before encoding (buffer under the real 256
word-piece limit, since word-piece tokenization can split words) by truncating the
assembled string, not by dropping whole sections — title/skills naturally survive because
they're written first.

Fix the failure-sentinel inconsistency along the way: keep
`generate_profile_embedding` returning `[]` on failure (existing behavior,
[embeddings.py:59](backend/services/embeddings.py#L59)) since `jobs.py` already checks
`if not profile_embedding` truthily — no caller changes needed.

## 2. Turn the relevance threshold back on (`backend/routers/jobs.py`)

- Add a module-level constant `MATCH_THRESHOLD = 0.45` near the top of the file (below the
  `CONFIGURED_PROVIDERS` block).
- Change the call at [jobs.py:102](backend/routers/jobs.py#L102) to
  `match_jobs(profile_embedding, match_threshold=MATCH_THRESHOLD, match_count=40)`.
- Do not add any padding/fallback logic when the result list comes back short — fewer than
  15 results is correct behavior now.

## 3. Always embed on upsert (`backend/services/job_ingestion.py`)

Restructure the loop in `JobIngestionWorkflow.run` (currently
[job_ingestion.py:43-77](backend/services/job_ingestion.py#L43-L77)):

- Move the `generate_job_embedding` call out of the `else` (new-job) branch so it runs for
  **every** job, update or insert.
- If `generate_job_embedding` returns `None`, do **not** add the job to `jobs_to_upsert` —
  `continue` to the next job — and increment `stats.skipped` (the field already exists on
  `IngestionStatistics`, just currently dead).
- Keep the existing `stats.updated` / `stats.inserted` bookkeeping as-is; it's orthogonal
  to embedding success.
- Keep the existing `if not job_dict.get("embedding"): job_dict.pop(...)` safety line —
  it becomes unreachable for the `None` case once skipped jobs never reach it, but leave it
  as a defensive no-op rather than removing it, since it's cheap and harmless.

## 4. Clean up ingestion sources

**`backend/routers/jobs.py`**
- Remove `MockJobProvider()` from `CONFIGURED_PROVIDERS`
  ([jobs.py:27-30](backend/routers/jobs.py#L27-L30)) and drop the now-unused
  `from backend.services.job_providers.mock_provider import MockJobProvider` import
  ([jobs.py:8](backend/routers/jobs.py#L8)).

**`backend/db/supabase_client.py`**
- Add a new helper, following the style of `get_profile_data`
  ([supabase_client.py:79-88](backend/db/supabase_client.py#L79-L88)):
  ```python
  def get_all_preferred_role_titles() -> List[str]:
      """Distinct preferred_job_roles[].title values across every profile."""
  ```
  Selects `profile_data` across all rows in `profiles`, pulls
  `profile_data["preferred_job_roles"][].title` out of each, and returns the deduplicated
  list. Wrapped in the same `try/except` + `logger.exception` pattern as the rest of the
  file, returning `[]` on failure.

**`backend/services/scheduler.py`**
- In `run_job_ingestion`, replace the unqualified `workflow.run()` with: fetch distinct
  role titles via the new `get_all_preferred_role_titles()`, and if the list is non-empty,
  call `workflow.run(query=role_title)` once per distinct title, accumulating/logging stats
  per role. If there are no profiles/roles, log that and return — never fall back to an
  unqualified `workflow.run()`.

## Constraints carried through every change

- No database schema changes, no migrations.
- No frontend changes.
- No unrelated refactors/renames — keep the diff tight.
- Preserve existing logging style (`logger.exception(...)` on caught errors).

## Verification

1. `python -m pytest tests/ -q` must pass, including two new test files:
   - `tests/test_embeddings.py` — covers the rewritten `generate_profile_embedding`: correct
     `personal_info.summary` extraction, skills flattening across `SkillCategory` entries,
     title/skills-first ordering, and truncation behavior on an oversized profile.
   - `tests/test_job_ingestion.py` — covers: embedding runs on both insert and update paths,
     a job is skipped (not upserted) and `stats.skipped` increments when
     `generate_job_embedding` returns `None`.
2. Write a throwaway script (e.g. in the scratchpad dir) that loads one real profile row via
   `get_profile_data`, builds the embedding text both the old way and the new way, and
   prints both strings side by side for a manual sanity check — then delete the script.
3. Grep the repo to confirm zero remaining hits for `match_threshold=-1.0` and zero
   remaining `MockJobProvider` imports under `backend/routers/`.
4. End with a summary of each change and `git diff --stat`.
