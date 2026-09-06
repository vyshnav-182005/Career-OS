#!/usr/bin/env python3
"""
Deletes cached job_matches rows that hold a feature-ranking fallback rather
than a real LLM verdict.

rank_jobs used to persist fallback results alongside genuine ones. Because the
cache is consulted before the LLM and is keyed on profile_version, a fallback
written during a provider outage was served back on every later request and
blocked the retry that would have replaced it - so a transient failure became
permanently degraded results ("the AI reviewer was unavailable" on the card).

rank_jobs no longer caches fallbacks, so no new rows like this are created.
This script clears the ones written before that fix - notably during the
2026-08-26 retirement of meta/llama-3.1-8b-instruct, when every call returned
410 Gone. The rows are pure cache: deleting them makes the next
/jobs/recommended request re-rank those jobs with the working model.

    python scripts/purge_fallback_job_matches.py           # report only
    python scripts/purge_fallback_job_matches.py --delete  # actually delete
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.db.supabase_client import get_supabase_client  # noqa: E402

# The sentence _fallback_ranked_job() puts in `reason`. Matching on it is what
# distinguishes a fallback row from a real verdict; nothing else in the row
# records where the result came from.
FALLBACK_MARKER = "the AI reviewer was unavailable"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--delete", action="store_true", help="delete the rows instead of only reporting them")
    args = parser.parse_args()

    client = get_supabase_client()
    pattern = f"%{FALLBACK_MARKER}%"

    total = client.table("job_matches").select("id", count="exact").limit(1).execute().count
    stale = (
        client.table("job_matches")
        .select("id", count="exact")
        .like("reason", pattern)
        .limit(1)
        .execute()
        .count
    )

    print(f"job_matches rows total     : {total}")
    print(f"cached fallback rows       : {stale}")

    if not stale:
        print("\nNothing to purge.")
        return 0

    if not args.delete:
        print("\nRe-run with --delete to remove them. The next /jobs/recommended")
        print("request will re-rank those jobs with the live model.")
        return 0

    deleted = client.table("job_matches").delete().like("reason", pattern).execute()
    remaining = (
        client.table("job_matches")
        .select("id", count="exact")
        .like("reason", pattern)
        .limit(1)
        .execute()
        .count
    )
    print(f"\nDeleted {len(deleted.data)} rows; fallback rows remaining: {remaining}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
