"""
Backfills role_family, skills and content_hash on existing rows in public.jobs.

Safe to re-run: every row's values are recomputed from its current
title/company/description, so re-running just rewrites the same values unless
the underlying job data or the taxonomy changed.

Run this after any change to backend/services/taxonomy.py. Stored jobs are
classified and skill-mined once, at ingest, so they otherwise keep the
taxonomy that existed on the day they were fetched - which is how 69% of the
table ended up with no role_family and every non-software posting ended up
with no skills.

Usage:
    python -m scripts.backfill_job_families                  # families + skills + embeddings
    python -m scripts.backfill_job_families --families-only  # classification only, much faster
"""

import argparse
import logging

from backend.db.supabase_client import get_supabase_client
from backend.services import taxonomy
from backend.services.embeddings import generate_job_embedding
from backend.services.job_ingestion import compute_content_hash

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BATCH_SIZE = 200


def backfill(families_only: bool = False) -> None:
    """
    families_only re-runs classification alone, writing only the rows whose
    role_family actually changed. Skills and embeddings are left untouched, so
    it finishes in a fraction of the time - use it after a change that only
    affects FAMILY_TITLE_PATTERNS, and the full pass after a change to
    SKILL_ALIASES.
    """
    client = get_supabase_client()
    offset = 0
    total_updated = 0

    while True:
        # order("id") is required for stable pagination: without an explicit
        # order, PostgREST doesn't guarantee row order is consistent across
        # separate .range() calls, so offset-based paging can silently skip
        # or duplicate rows between batches.
        columns = "id, title, role_family" if families_only else "id, title, company, description, skills"
        result = (
            client.table("jobs")
            .select(columns)
            .order("id")
            .range(offset, offset + BATCH_SIZE - 1)
            .execute()
        )
        rows = result.data or []
        if not rows:
            break

        for row in rows:
            role_family = taxonomy.classify_title(row.get("title") or "")

            if families_only:
                if role_family == row.get("role_family"):
                    continue
                try:
                    client.table("jobs").update({"role_family": role_family}).eq("id", row["id"]).execute()
                    total_updated += 1
                except Exception:
                    logger.exception("Failed to reclassify job id=%s", row["id"])
                continue

            # Skills are re-mined from the description, not carried over. They
            # were extracted at ingest time against whatever vocabulary existed
            # then, so a stored job keeps the gaps of that vocabulary forever -
            # every security and hardware posting held an empty skills list,
            # which zeroes the skill_overlap feature for exactly the candidates
            # this backfill is meant to help. Re-deriving here is also what
            # keeps stored rows equal to what ingestion would write today.
            skills = taxonomy.extract_skills(row.get("description")) or (row.get("skills") or [])
            content_hash = compute_content_hash(
                row.get("title") or "",
                row.get("company") or "",
                row.get("description"),
                skills,
            )
            payload = {"role_family": role_family, "skills": skills, "content_hash": content_hash}

            # The stored embedding is built from title + skills + description, so
            # re-mining skills above makes it stale. Ingestion would normally
            # re-embed on a content_hash change, but this script writes the new
            # hash itself, so the next run sees no change and the stale vector
            # would survive indefinitely. Re-embedding costs ~10ms per job
            # against a DB write we are already making, so it happens here.
            # A failure leaves the existing vector alone rather than nulling it:
            # an unembedded job is invisible to vector matching entirely.
            try:
                embedding = generate_job_embedding(
                    row.get("title") or "", row.get("description") or "", skills
                )
                if embedding:
                    payload["embedding"] = embedding
            except Exception:
                logger.exception("Failed to re-embed job id=%s; keeping stored vector", row["id"])

            try:
                client.table("jobs").update(payload).eq("id", row["id"]).execute()
                total_updated += 1
            except Exception:
                logger.exception("Failed to backfill job id=%s", row["id"])

        logger.info("Scanned %d rows; %d updated so far...", offset + len(rows), total_updated)

        if len(rows) < BATCH_SIZE:
            break
        offset += BATCH_SIZE

    logger.info("Backfill complete. %d rows updated.", total_updated)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--families-only",
        action="store_true",
        help="only re-classify role_family, writing just the rows that changed",
    )
    backfill(families_only=parser.parse_args().families_only)
