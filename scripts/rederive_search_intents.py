#!/usr/bin/env python3
"""
Re-runs the Profile Intelligence agent for existing profiles so their stored
search_intent reflects the current taxonomy.

search_intent is written once, when a resume is uploaded, and then reused for
every recommendation. So a profile created before a taxonomy change keeps the
families that existed at upload time - an ECE candidate parsed when the only
hardware family was "embedded" never gets "hardware-electronics", and the
excluded_families list keeps whatever the old prompt asked for.

Re-deriving also changes the profile_version, which invalidates that user's
job_matches cache, so the next /jobs/recommended re-ranks against the new
intent rather than serving verdicts computed under the old one.

    python scripts/rederive_search_intents.py           # report only
    python scripts/rederive_search_intents.py --apply   # re-run the agent
    python scripts/rederive_search_intents.py --apply --user <uuid>
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.agents.profile_intelligence_agent import run_profile_intelligence  # noqa: E402
from backend.db.supabase_client import get_supabase_client  # noqa: E402


def _intent(profile_data: dict | None) -> dict:
    return ((profile_data or {}).get("search_intent") or {})


def _describe(user_id: str, profile_data: dict | None) -> str:
    intent = _intent(profile_data)
    return (
        f"  {user_id[:8]}..  families={intent.get('role_families')}  "
        f"excluded={len(intent.get('excluded_families') or [])}  "
        f"seniority={intent.get('seniority')}"
    )


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="actually re-run the agent")
    parser.add_argument("--user", help="limit to one user_id")
    args = parser.parse_args()

    client = get_supabase_client()
    query = client.table("profiles").select("user_id, profile_data")
    if args.user:
        query = query.eq("user_id", args.user)
    rows = query.execute().data or []

    if not rows:
        print("No profiles found.")
        return 0

    print(f"{len(rows)} profile(s) - current search_intent:")
    for row in rows:
        print(_describe(row["user_id"], row.get("profile_data")))

    if not args.apply:
        print("\nRe-run with --apply to regenerate these against the current taxonomy.")
        return 0

    print()
    for row in rows:
        user_id = row["user_id"]
        try:
            await run_profile_intelligence(user_id)
            print(f"re-derived {user_id[:8]}..")
        except Exception as exc:
            print(f"FAILED {user_id[:8]}..: {type(exc).__name__}: {exc}")

    refreshed = client.table("profiles").select("user_id, profile_data")
    if args.user:
        refreshed = refreshed.eq("user_id", args.user)
    print("\nsearch_intent after:")
    for row in refreshed.execute().data or []:
        print(_describe(row["user_id"], row.get("profile_data")))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
