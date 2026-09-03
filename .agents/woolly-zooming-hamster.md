# Phase 1 — Structured search intent

## Context

`.agents/job-matching-rework-prompts.md` lays out a multi-phase rework of CareerOS's job
recommendation engine. Phase 0 (fix profile embedding, turn the relevance threshold back
on, always embed on upsert, drop the mock provider / untargeted ingestion) is already done
in the working tree — `backend/routers/jobs.py` has `MATCH_THRESHOLD = 0.45`,
`job_ingestion.py` always regenerates embeddings, and `scheduler.py` fetches per role title.

Phase 1 replaces free-text role titles with a structured, machine-usable `SearchIntent`
taxonomy and classifies every ingested job into the same taxonomy. **No filtering logic
yet** — this phase only produces data that Phase 2 will filter on. It's pure groundwork:
a new deterministic taxonomy module, an LLM-populated `search_intent` on the profile, new
job columns + classification at ingest time, and a backfill script for existing rows.

## What already exists (confirmed by reading the code)

- `backend/agents/profile_intelligence_agent.py` — LLM call via NVIDIA NIM
  (`OpenAI(base_url=".../v1")`), `response_format={"type": "json_object"}`, markdown-fence
  stripping + `json.loads`, temperature 0.2. New prompt fields must follow this exact
  pattern.
- `backend/models/profile.py` — `ProfileIntelligence` wraps `original_resume`,
  `preferred_job_roles`, `strengths`, `insights`. `preferred_job_roles` stays untouched —
  `search_intent` is additive.
- `backend/models/resume.py` — `ParsedResume.skills` is `list[SkillCategory]`
  (`{category, skills: [...]}`), not a flat list. `experience[].title`,
  `projects[].technologies` are the other sources the taxonomy prompt needs to reference.
- `backend/models/job.py` — `NormalizedJob`, `IngestionStatistics` (already has `skipped`).
- `backend/services/job_ingestion.py` — embeds every job on upsert already (Phase 0 done);
  this is where `role_family`, `source_query`, `last_seen_at`, `content_hash` get set.
- `backend/db/supabase_client.py` — `get_active_provider_job_ids(provider)` returns just
  IDs; needs to become hash-aware for the re-embed-skip logic. `upsert_jobs` upserts
  whatever keys are in each dict, so omitting a key from the payload leaves that column
  untouched on conflict — this is the mechanism for skipping re-embedding.
- `database/performance_indexes.sql` — the idempotent migration style to follow
  (`CREATE INDEX IF NOT EXISTS`, `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`).
- `tests/test_job_ingestion.py` — `unittest.TestCase` + `unittest.mock.patch.object`,
  mocking `job_ingestion.generate_job_embedding`, `get_active_provider_job_ids`,
  `upsert_jobs`, `delete_expired_jobs`. Will need updating for the renamed/hash-aware
  lookup function.

## Build plan

### 1. `backend/services/taxonomy.py` (new file)

Deterministic Python, no LLM/network calls anywhere in this module.

- `ROLE_FAMILIES`: the 14 slugs from the spec — `frontend, backend, fullstack, mobile,
  data-engineering, data-science, ml-engineering, devops-sre, cloud-infra, qa-testing,
  security, embedded, product-design, technical-writing`.
- `FAMILY_TITLE_PATTERNS`: `dict[str, list[str]]` of case-insensitive regexes per family,
  e.g. `devops-sre` matches `devops`, `site reliability`, `\bsre\b`, `platform engineer`,
  `infrastructure engineer`; `qa-testing` matches `\bqa\b`, `quality assurance`,
  `test engineer`, `sdet`. Keep patterns specific enough to avoid `qa-testing` swallowing
  `automation engineer` (ambiguous — leave unmatched, i.e. `None`, rather than guess).
- `ADJACENT_FAMILIES`: `dict[str, list[str]]` sideways-move map, e.g.
  `frontend <-> fullstack`, `backend <-> fullstack`, `data-science <-> ml-engineering`,
  `devops-sre <-> cloud-infra`. `devops-sre` must not list any application-dev family and
  no application-dev family may list `devops-sre` back.
- `SKILL_ALIASES`: `dict[str, list[str]]` canonical-skill -> aliases, covering common stacks
  (languages, JS/Python frameworks, cloud/container/IaC tooling, databases, data/ML
  libraries, testing tools, mobile). Large but flat — no nested structure needed.
- `canonicalize_skills(raw: list[str]) -> list[str]`: build a reverse lookup
  (`alias.lower() -> canonical`) once at module load; unmatched skills pass through
  title-cased/trimmed rather than being dropped; de-duplicate while preserving order.
- `classify_title(title: str) -> str | None`: iterate `FAMILY_TITLE_PATTERNS` and return the
  first confident match; `None` (not a guess) when nothing matches.

### 2. `SearchIntent` model — `backend/models/profile.py`

```python
class SearchIntent(BaseModel):
    role_families: list[str] = Field(default_factory=list)
    excluded_families: list[str] = Field(default_factory=list)
    seniority: str = "mid"  # intern | junior | mid | senior | lead
    must_have_skills: list[str] = Field(default_factory=list)
    nice_to_have_skills: list[str] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)
    work_mode: str = "any"  # onsite | hybrid | remote | any
    employment_types: list[str] = Field(default_factory=list)
```

Add `search_intent: SearchIntent | None = None` to `ProfileIntelligence` — `Optional` so
existing rows without it still deserialize.

### 3. Extend the Profile Intelligence Agent

`backend/agents/profile_intelligence_agent.py`:

- Extend `PROFILE_INTELLIGENCE_PROMPT` to also request a `search_intent` object matching
  the `SearchIntent` shape. Interpolate `taxonomy.ROLE_FAMILIES` into the prompt text and
  instruct the model to choose `role_families`/`excluded_families` **only** from that list —
  never invent a slug.
- Explicitly instruct the model to populate `excluded_families` with families the résumé
  shows no evidence for, and explain in the prompt that this negative signal is deliberate
  (it's what later phases hard-filter on).
- Instruct it to derive `seniority` from total years of experience visible in the résumé
  dates already present in `resume_json` (no new code-side date math needed — the LLM has
  the experience entries).
- After `json.loads`, validate server-side before constructing `SearchIntent`: drop any
  family not in `taxonomy.ROLE_FAMILIES` (both lists), run skill lists through
  `taxonomy.canonicalize_skills`, coerce `seniority`/`work_mode` to their allowed enums with
  a safe default, and default every missing field. Never trust the LLM's output shape
  directly — same spirit as the existing malformed-JSON handling in this file.
- Pass `search_intent=search_intent` into the constructed `ProfileIntelligence`.

### 4. Job columns + classification

**Migration** — `database/job_matching_migration.sql` (new file, idempotent, follows
`performance_indexes.sql` style):
```sql
ALTER TABLE public.jobs ADD COLUMN IF NOT EXISTS role_family TEXT;
ALTER TABLE public.jobs ADD COLUMN IF NOT EXISTS source_query TEXT;
ALTER TABLE public.jobs ADD COLUMN IF NOT EXISTS last_seen_at TIMESTAMPTZ DEFAULT now();
ALTER TABLE public.jobs ADD COLUMN IF NOT EXISTS content_hash TEXT;

CREATE INDEX IF NOT EXISTS idx_jobs_status_role_family ON public.jobs (status, role_family);
CREATE INDEX IF NOT EXISTS idx_jobs_last_seen_at ON public.jobs (last_seen_at);
```
I will show you this file before you run it in the Supabase SQL editor — not applied
automatically.

**`backend/models/job.py`** — add `role_family: Optional[str] = None`,
`source_query: Optional[str] = None`, `last_seen_at: Optional[datetime] = None`,
`content_hash: Optional[str] = None` to `NormalizedJob`.

**`backend/services/job_ingestion.py`**:
- Add a `_compute_content_hash(job) -> str`: `sha256` of `title + company + description +
  sorted(skills)`, joined with a separator.
- Replace the `get_active_provider_job_ids` call with a new
  `get_active_provider_job_hashes(provider) -> dict[str, str]` (provider_job_id ->
  content_hash) from `supabase_client.py`; `existing_active_ids` becomes
  `set(existing_hashes.keys())`, preserving today's insert/update stats logic unchanged.
- For every job: set `role_family = taxonomy.classify_title(job.title)`,
  `source_query = query`, `last_seen_at = datetime.now(timezone.utc)`,
  `content_hash = _compute_content_hash(job)`.
- If `existing_hashes.get(job.provider_job_id) == job.content_hash` (unchanged content on
  an already-active job): **skip calling `generate_job_embedding`** and pop the
  `"embedding"` key from `job_dict` before upserting, so the upsert leaves the existing
  vector column untouched. Otherwise keep today's Phase-0 behavior (generate, skip-and-count
  the job if it comes back `None`).

**`backend/db/supabase_client.py`** — replace `get_active_provider_job_ids` with
`get_active_provider_job_hashes(provider: str) -> dict[str, str]` (`select
provider_job_id, content_hash` instead of just `provider_job_id`), same
error-handling/logging convention as the function it replaces.

**`tests/test_job_ingestion.py`** — update the three existing tests to patch
`get_active_provider_job_hashes` instead of `get_active_provider_job_ids`; add a new test
asserting that a job whose `content_hash` matches the stored hash is upserted **without**
an `embedding` key in its payload and without a `generate_job_embedding` call, while a
changed/new job still gets embedded.

### 5. `scripts/backfill_job_families.py` (new file)

Standalone, re-runnable script (matches the `scripts/` dir's existing standalone-script
style): pages through `jobs` in batches (e.g. 200 rows), computes `role_family` via
`taxonomy.classify_title` and `content_hash` via the same hashing logic used in
`job_ingestion.py` (factor `_compute_content_hash` so both share it — e.g. move it to
`taxonomy.py` or a small shared helper), and updates rows in batches via the Supabase
client. Safe to re-run: recomputing and re-writing the same value is a no-op.

## Tests

- `tests/test_taxonomy.py` (new): `classify_title` against ~20 real-world job titles across
  all 14 families including deliberately ambiguous ones ("Consultant", "Analyst" ->
  `None`); `canonicalize_skills` alias collapsing (e.g. "ReactJS"/"React.js"/"react" all ->
  `"React"`); `ADJACENT_FAMILIES` sanity check that `devops-sre` has no application-dev
  family as a neighbor.
- Updated `tests/test_job_ingestion.py` as described above.
- `python -m pytest tests/ -q` must pass.

## Verification before calling this done

1. Show the generated `database/job_matching_migration.sql` for review (not run by me).
2. Run the profile intelligence agent against one real profile row from Supabase and print
   the resulting `search_intent` JSON so the families/exclusions can be sanity-checked.
3. `python -m pytest tests/ -q` green.
4. `git diff --stat` summary of all touched files.

## Explicit non-goals for this phase

- No filtering added to `match_jobs` or `/jobs/recommended` (Phase 2).
- `preferred_job_roles` is not removed or rewritten.
- No LLM calls inside `taxonomy.py` or at job-ingest classification time.
