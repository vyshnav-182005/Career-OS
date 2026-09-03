# Baseline (pre-Phase 2)

**Not yet recorded.** Requires running `python -m scripts.eval.run_eval` and
`python -m scripts.eval.score` against a real Supabase project with `SUPABASE_URL` /
`SUPABASE_SERVICE_KEY` set and an already-ingested `jobs` table — there is no local
Postgres in this repo, so this can't be produced automatically here.

To record it:
1. Run the two commands above in `legacy` mode (i.e. before `backend/services/job_matching.py`
   exists, or with it temporarily unimportable).
2. Paste the printed table below, with the date and which `jobs` table snapshot it ran
   against.
3. After Phase 2 lands, re-run both commands (now in `v2` mode) and compare
   `family_purity@10` / `cross_family_leak@10` side by side in this file.

```
<paste `python -m scripts.eval.score` output here>
```
