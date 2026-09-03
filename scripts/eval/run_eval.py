"""
Offline evaluation harness for job-matching retrieval. Runs each fixture résumé
through the REAL production retrieval path (never a reimplementation) and dumps
the top 20 results per fixture for scoring by score.py.

Read-only against Supabase: never writes, upserts, or deletes.

Usage:
    python -m scripts.eval.run_eval
"""

import json
import logging
import os
from datetime import datetime, timezone

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")
RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")
TOP_N = 20

# job_matching.retrieve_candidates (Phase 2) doesn't exist until Phase 2 merges.
# Falling back here means this harness works today and automatically starts
# exercising the new hybrid path the moment job_matching.py lands - no edit
# needed to this file at the Phase 2 boundary.
try:
    from backend.services.job_matching import retrieve_candidates
    RETRIEVAL_MODE = "v2"
except ImportError:
    from backend.services.embeddings import generate_profile_embedding
    from backend.db.supabase_client import match_jobs
    from backend.routers.jobs import MATCH_THRESHOLD
    RETRIEVAL_MODE = "legacy"


def load_fixtures() -> dict[str, dict]:
    fixtures = {}
    for filename in sorted(os.listdir(FIXTURES_DIR)):
        if not filename.endswith(".json") or filename == "expected.json":
            continue
        name = filename[: -len(".json")]
        with open(os.path.join(FIXTURES_DIR, filename), "r", encoding="utf-8") as f:
            fixtures[name] = json.load(f)
    return fixtures


def build_profile_data(resume: dict) -> dict:
    """
    Wraps a raw ParsedResume-shaped fixture the way profile_data is shaped
    once it's persisted: original_resume + the enrichment fields the
    production embedding/retrieval code reads. preferred_job_roles and
    search_intent are intentionally empty/None - fixtures simulate a resume
    that hasn't been through the (LLM-backed) profile intelligence agent, so
    both the legacy embedding path and Phase 2's search_intent=None fallback
    get exercised.
    """
    return {
        "original_resume": resume,
        "preferred_job_roles": [],
        "strengths": [],
        "search_intent": None,
    }


def _dump_job(job: dict) -> dict:
    return {
        "id": job.get("id"),
        "title": job.get("title"),
        "company": job.get("company"),
        "similarity": job.get("similarity"),
        "role_family": job.get("role_family"),
    }


def run_fixture_legacy(name: str, profile_data: dict) -> list[dict]:
    embedding = generate_profile_embedding(profile_data)
    if not embedding:
        logger.warning("No embedding generated for fixture %s", name)
        return []
    matched = match_jobs(embedding, match_threshold=MATCH_THRESHOLD, match_count=40)
    return [_dump_job(job) for job in matched[:TOP_N]]


def run_fixture_v2(name: str, profile_data: dict) -> list[dict]:
    scored_jobs = retrieve_candidates(user_id=f"eval-{name}", profile_data=profile_data)
    if scored_jobs is None:
        logger.warning("No embedding generated for fixture %s", name)
        return []
    dumped = []
    for scored_job in scored_jobs[:TOP_N]:
        row = _dump_job(scored_job.job.model_dump())
        row["score"] = scored_job.score
        row["features"] = scored_job.features.model_dump()
        dumped.append(row)
    return dumped


def main() -> None:
    os.makedirs(RESULTS_DIR, exist_ok=True)
    fixtures = load_fixtures()
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    logger.info("Running eval in %s mode against %d fixtures", RETRIEVAL_MODE, len(fixtures))

    for name, resume in fixtures.items():
        profile_data = build_profile_data(resume)
        if RETRIEVAL_MODE == "v2":
            jobs = run_fixture_v2(name, profile_data)
        else:
            jobs = run_fixture_legacy(name, profile_data)

        out_path = os.path.join(RESULTS_DIR, f"{name}_{timestamp}.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump({"fixture": name, "mode": RETRIEVAL_MODE, "jobs": jobs}, f, indent=2)

        logger.info("%s: %d jobs -> %s", name, len(jobs), out_path)


if __name__ == "__main__":
    main()
