"""
Backfills role_family and content_hash on existing rows in public.jobs.

Safe to re-run: every row's role_family/content_hash is recomputed from its
current title/company/description/skills, so re-running just rewrites the
same values unless the underlying job data changed.

Usage:
    python -m scripts.backfill_job_families
"""

import logging

from backend.db.supabase_client import get_supabase_client
from backend.services import taxonomy
from backend.services.job_ingestion import compute_content_hash

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BATCH_SIZE = 200


def backfill() -> None:
    client = get_supabase_client()
    offset = 0
    total_updated = 0

    while True:
        # order("id") is required for stable pagination: without an explicit
        # order, PostgREST doesn't guarantee row order is consistent across
        # separate .range() calls, so offset-based paging can silently skip
        # or duplicate rows between batches.
        result = (
            client.table("jobs")
            .select("id, title, company, description, skills")
            .order("id")
            .range(offset, offset + BATCH_SIZE - 1)
            .execute()
        )
        rows = result.data or []
        if not rows:
            break

        for row in rows:
            role_family = taxonomy.classify_title(row.get("title") or "")
            content_hash = compute_content_hash(
                row.get("title") or "",
                row.get("company") or "",
                row.get("description"),
                row.get("skills") or [],
            )
            try:
                client.table("jobs").update(
                    {"role_family": role_family, "content_hash": content_hash}
                ).eq("id", row["id"]).execute()
                total_updated += 1
            except Exception:
                logger.exception("Failed to backfill job id=%s", row["id"])

        logger.info("Backfilled %d/%d rows so far...", total_updated, offset + len(rows))

        if len(rows) < BATCH_SIZE:
            break
        offset += BATCH_SIZE

    logger.info("Backfill complete. %d rows updated.", total_updated)


if __name__ == "__main__":
    backfill()
