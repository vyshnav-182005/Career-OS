# Baseline

## 2026-09-04 — after the cross-domain taxonomy work

Run against the live `CareerOS-Database` jobs table (2,894 rows) in `v2` mode,
immediately after broadening the taxonomy beyond software, opening the
`role_family IS NULL` retrieval gate, and re-running
`scripts/backfill_job_families.py`.

```
fixture              mode       n  purity@10  leak@10  mean_sim@10
------------------------------------------------------------------
cybersecurity_offensive v2        20       0.80     0.20        0.584
data_analyst         v2        20       0.10     0.20        0.541
devops_control       v2        20       1.00     0.00        0.706
ece_hardware         v2        20       0.80     0.10        0.619
java_backend         v2        20       0.80     0.00        0.636
mechanical_design    v2        20       0.10     0.90        0.541
ml_engineer          v2        20       1.00     0.00        0.669
qa_automation        v2        20       0.00     0.90        0.545
react_frontend       v2        20       0.10     0.30        0.616
------------------------------------------------------------------
empty_rate: 0.00
mean family_purity@10: 0.52
mean cross_family_leak@10: 0.29
```

### How to read this

**`empty_rate: 0.00` is the number this run was about.** Before this work a
cybersecurity résumé returned about 2 matches and an ECE résumé returned none,
because their job titles classified as nothing and the retrieval gate drops a
NULL `role_family`. Every fixture now returns results.

**Purity here is not the production number.** `run_eval.build_profile_data`
sets `search_intent: None` on purpose, so these runs have no family gate at all
— `_family_fit` returns a flat 0.5 and ranking is essentially pure semantic
similarity. The gated path a real user gets is much tighter: measured the same
day against the three real profiles, the cybersecurity account retrieved 40/40
candidates in `security`, and the ECE account 37/40 in
`hardware-electronics`/`embedded`.

**Low purity tracks low inventory, not bad matching.** The weak fixtures are
exactly the families with almost nothing in the table to match against:
`mechanical` (3 jobs), `qa-testing` (3), `data-science` (8), `frontend` (24).
With nothing in-family to rank, semantic-only retrieval fills the top 10 with
neighbours. Re-check these after the seeded ingestion in
`taxonomy.DOMAIN_SEED_QUERIES` and the hardware/aerospace boards added to
`backend/data/ats_companies.json` have had time to populate the table; a family
that stays at 0.10 once it has real inventory is a genuine matching bug.

### Role-family distribution at the time of this run

2,894 jobs, 1,958 classified (68%, up from 904 / 31% before the taxonomy work):

```
software-general 918   backend 297   ml-engineering 238   security 179
devops-sre 128   fullstack 68   hardware-electronics 34   embedded 30
frontend 24   data-engineering 9   data-science 8   product-design 7
cloud-infra 5   robotics-controls 5   qa-testing 3   mechanical 3   aerospace 2
(unclassified 936 — predominantly non-engineering: sales, hospitality, legal, HR)
```

## Pre-Phase-2 baseline

Never recorded; `backend/services/job_matching.py` already existed by the time
this harness was first run against real data, so there is no `legacy`-mode
table to compare against.
