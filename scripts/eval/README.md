# Job-matching evaluation harness

Offline, deterministic scoring of the job recommendation retrieval path against 9
synthetic fixture résumés spanning distinct role families (`fixtures/*.json`, expected
families in `fixtures/expected.json`). Read-only against Supabase; no LLM calls in
scoring.

Three of the fixtures — `cybersecurity_offensive`, `ece_hardware` and
`mechanical_design` — are non-software on purpose. The taxonomy was originally
software-only, so résumés from those branches of engineering classified as nothing,
were dropped by the `role_family` gate, and returned almost no matches. Keep a
fixture per engineering branch here so that regression is caught by `empty_rate`
rather than by a user with an empty Jobs page.

## Running

```
python -m scripts.eval.run_eval
python -m scripts.eval.score
```

`run_eval.py` imports the real production retrieval code — `backend.services.job_matching.retrieve_candidates`
if it exists (Phase 2+), otherwise falls back to the Phase-0 path
(`generate_profile_embedding` + `match_jobs`). It writes one
`results/<fixture>_<timestamp>.json` per fixture per run; nothing is deleted, so
`score.py` always reads the most recent file per fixture.

Both scripts require real `SUPABASE_URL`/`SUPABASE_SERVICE_KEY` credentials and an
already-ingested `jobs` table — there is no local/mock Postgres in this repo, so a
baseline run has to be done by a human with prod (or a scratch) Supabase access, not by
CI.

## Metrics

- `family_purity@10` — share of the top 10 whose `role_family` is in the fixture's
  expected families. The direct DevOps-contamination metric.
- `cross_family_leak@10` — share of the top 10 in a family that's neither expected nor
  adjacent (per `taxonomy.ADJACENT_FAMILIES`). Should trend to zero.
- `empty_rate` — fraction of fixtures returning fewer than 3 results.
- `mean_similarity@10`.

## Manual precision@10

```
python -m scripts.eval.score --label
```
writes `results/label.csv` with the current top-10 per fixture. Fill in the `relevant`
column (0/1) by hand, then:
```
python -m scripts.eval.score --label results/label.csv
```
prints precision@10 per fixture.

## Baseline

See `baseline.md` — the Phase-0/1 numbers recorded before Phase 2 (hybrid retrieval +
hard gates) landed, for before/after comparison.
