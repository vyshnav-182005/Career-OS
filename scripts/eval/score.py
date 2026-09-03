"""
Scores the results dumped by run_eval.py against scripts/eval/fixtures/expected.json.

Metrics (all computed over each fixture's top 10 results):
    family_purity@10     - share whose role_family is in the fixture's expected families
    cross_family_leak@10 - share whose role_family is neither expected nor adjacent to
                            an expected family (per taxonomy.ADJACENT_FAMILIES). A job
                            with no role_family (unclassified) counts toward neither
                            metric's numerator - it's unknown, not confirmed contamination.
    empty_rate           - fraction of fixtures returning fewer than 3 results
    mean_similarity@10   - mean of the "similarity" field across all fixtures' top 10

No DB or LLM calls - pure functions over the JSON run_eval.py already produced.

Usage:
    python -m scripts.eval.score                  # prints the metric table
    python -m scripts.eval.score --label           # writes a CSV to hand-label
    python -m scripts.eval.score --label results.csv  # reads a filled-in CSV, prints precision@10
"""

import csv
import json
import os
import sys
from collections import defaultdict

from backend.services.taxonomy import ADJACENT_FAMILIES

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")
RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")
TOP_K = 10
EMPTY_RESULT_THRESHOLD = 3
LABEL_CSV_PATH = os.path.join(os.path.dirname(__file__), "results", "label.csv")


def load_expected() -> dict[str, list[str]]:
    with open(os.path.join(FIXTURES_DIR, "expected.json"), "r", encoding="utf-8") as f:
        return json.load(f)


def latest_result_per_fixture() -> dict[str, dict]:
    """Picks the most recently written results file for each fixture name."""
    by_fixture: dict[str, list[str]] = defaultdict(list)
    if not os.path.isdir(RESULTS_DIR):
        return {}
    for filename in os.listdir(RESULTS_DIR):
        if not filename.endswith(".json"):
            continue
        # "<fixture>_<timestamp>.json" -> fixture name
        name = filename.rsplit("_", 1)[0]
        by_fixture[name].append(filename)

    latest = {}
    for name, filenames in by_fixture.items():
        newest = sorted(filenames)[-1]
        with open(os.path.join(RESULTS_DIR, newest), "r", encoding="utf-8") as f:
            latest[name] = json.load(f)
    return latest


def _is_adjacent(family: str, expected_families: list[str]) -> bool:
    return any(family in ADJACENT_FAMILIES.get(expected, []) for expected in expected_families)


def family_purity_at_10(jobs: list[dict], expected_families: list[str]) -> float:
    top = jobs[:TOP_K]
    if not top:
        return 0.0
    hits = sum(1 for job in top if job.get("role_family") in expected_families)
    return hits / len(top)


def cross_family_leak_at_10(jobs: list[dict], expected_families: list[str]) -> float:
    top = jobs[:TOP_K]
    if not top:
        return 0.0
    leaks = sum(
        1 for job in top
        if job.get("role_family")
        and job["role_family"] not in expected_families
        and not _is_adjacent(job["role_family"], expected_families)
    )
    return leaks / len(top)


def mean_similarity_at_10(jobs: list[dict]) -> float:
    top = [job for job in jobs[:TOP_K] if job.get("similarity") is not None]
    if not top:
        return 0.0
    return sum(job["similarity"] for job in top) / len(top)


def empty_rate(results: dict[str, dict]) -> float:
    if not results:
        return 0.0
    empty = sum(1 for r in results.values() if len(r.get("jobs", [])) < EMPTY_RESULT_THRESHOLD)
    return empty / len(results)


def score_all() -> dict:
    expected = load_expected()
    results = latest_result_per_fixture()

    per_fixture = {}
    for name, result in results.items():
        expected_families = expected.get(name, [])
        jobs = result.get("jobs", [])
        per_fixture[name] = {
            "mode": result.get("mode"),
            "n_results": len(jobs),
            "family_purity@10": family_purity_at_10(jobs, expected_families),
            "cross_family_leak@10": cross_family_leak_at_10(jobs, expected_families),
            "mean_similarity@10": mean_similarity_at_10(jobs),
        }

    aggregate = {
        "empty_rate": empty_rate(results),
        "mean_family_purity@10": (
            sum(v["family_purity@10"] for v in per_fixture.values()) / len(per_fixture)
            if per_fixture else 0.0
        ),
        "mean_cross_family_leak@10": (
            sum(v["cross_family_leak@10"] for v in per_fixture.values()) / len(per_fixture)
            if per_fixture else 0.0
        ),
    }
    return {"per_fixture": per_fixture, "aggregate": aggregate}


def print_table(scores: dict) -> None:
    header = f"{'fixture':<20} {'mode':<8} {'n':>3} {'purity@10':>10} {'leak@10':>8} {'mean_sim@10':>12}"
    print(header)
    print("-" * len(header))
    for name, row in sorted(scores["per_fixture"].items()):
        print(
            f"{name:<20} {row['mode']:<8} {row['n_results']:>3} "
            f"{row['family_purity@10']:>10.2f} {row['cross_family_leak@10']:>8.2f} "
            f"{row['mean_similarity@10']:>12.3f}"
        )
    print("-" * len(header))
    agg = scores["aggregate"]
    print(f"empty_rate: {agg['empty_rate']:.2f}")
    print(f"mean family_purity@10: {agg['mean_family_purity@10']:.2f}")
    print(f"mean cross_family_leak@10: {agg['mean_cross_family_leak@10']:.2f}")


def write_label_csv() -> None:
    results = latest_result_per_fixture()
    rows = []
    for name, result in results.items():
        for job in result.get("jobs", [])[:TOP_K]:
            rows.append({
                "fixture": name,
                "job_id": job.get("id"),
                "title": job.get("title"),
                "company": job.get("company"),
                "role_family": job.get("role_family"),
                "relevant": "",
            })
    os.makedirs(os.path.dirname(LABEL_CSV_PATH), exist_ok=True)
    with open(LABEL_CSV_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["fixture", "job_id", "title", "company", "role_family", "relevant"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} rows to {LABEL_CSV_PATH} - fill in 'relevant' (0/1) and re-run "
          f"'python -m scripts.eval.score --label {LABEL_CSV_PATH}' to compute precision@10.")


def score_label_csv(csv_path: str) -> None:
    by_fixture: dict[str, list[int]] = defaultdict(list)
    with open(csv_path, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            relevant = row.get("relevant", "").strip()
            if relevant == "":
                continue
            by_fixture[row["fixture"]].append(int(relevant))

    print(f"{'fixture':<20} {'precision@10':>12}")
    for name, labels in sorted(by_fixture.items()):
        precision = sum(labels) / len(labels) if labels else 0.0
        print(f"{name:<20} {precision:>12.2f}")


def main() -> None:
    args = sys.argv[1:]
    if "--label" in args:
        idx = args.index("--label")
        csv_arg = args[idx + 1] if idx + 1 < len(args) else None
        if csv_arg:
            score_label_csv(csv_arg)
        else:
            write_label_csv()
        return

    scores = score_all()
    print_table(scores)


if __name__ == "__main__":
    main()
