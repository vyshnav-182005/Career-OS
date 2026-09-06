#!/usr/bin/env python3
"""
Collapses duplicate project entries that describe the same GitHub repo.

Resume parsing stores a project under the heading the resume used, with the
clone URL it listed ("https://github.com/me/Career-OS.git"). The GitHub scan
that follows stores the same repo under its real name with the API's html_url
("https://github.com/me/Career-OS"). The scan's duplicate check compared URLs
verbatim, so the ".git" suffix defeated it and one repo produced two cards in
the Projects section.

enrich_profile_with_github_projects now matches on the canonical owner/repo key
and renames matched entries to the repo name, so no new duplicates are written
and a re-scan self-heals a profile. This script applies the same merge to
profiles already stored, without waiting for the user's next GitHub scan.

    python scripts/dedupe_github_projects.py          # report only
    python scripts/dedupe_github_projects.py --write  # persist the merge
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.db.supabase_client import (  # noqa: E402
    _compute_profile_version,
    get_supabase_client,
)
from backend.services.github_enrichment import (  # noqa: E402
    _normalize_name,
    _repo_key,
    merge_repos_into_projects,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write", action="store_true", help="persist the merge instead of only reporting it"
    )
    args = parser.parse_args()

    client = get_supabase_client()
    rows = client.table("profiles").select("user_id, profile_data").execute().data or []

    total_removed = 0
    changed_profiles = 0

    for row in rows:
        user_id = row.get("user_id")
        profile_data = row.get("profile_data") or {}
        resume = profile_data.get("original_resume") or {}
        projects = resume.get("projects") or []
        if not projects:
            continue

        # No repos: pass 1 alone collapses the duplicates already stored.
        merged = merge_repos_into_projects(projects, [])
        if merged == projects:
            continue

        changed_profiles += 1
        removed = len(projects) - len(merged)
        total_removed += removed
        print(f"\n{user_id}: {len(projects)} -> {len(merged)} projects ({removed} merged)")

        for project in merged:
            name = project.get("name")
            key = _repo_key(project.get("url"))
            # The originals this entry absorbed, so that a rename reads as a
            # rename rather than looking like a deleted project.
            if key:
                sources = [o for o in projects if _repo_key(o.get("url")) == key]
            else:
                sources = [
                    o
                    for o in projects
                    if _normalize_name(o.get("name")) == _normalize_name(name)
                ]

            print(f"  {name!r}  {project.get('url')}")
            for source in sources:
                if source.get("name") != name:
                    print(f"      was  {source.get('name')!r}")

        if args.write:
            profile_data.setdefault("original_resume", resume)["projects"] = merged
            client.table("profiles").update(
                {
                    "profile_data": profile_data,
                    # job_matches is cached against this hash. Dropping the
                    # duplicate projects changes what the ranker sees, so the
                    # stale verdicts have to fall out of the cache with it.
                    "profile_version": _compute_profile_version(profile_data),
                }
            ).eq("user_id", user_id).execute()

    if not changed_profiles:
        print("No duplicate projects found.")
        return 0

    print(
        f"\n{changed_profiles} profile(s) changed, {total_removed} duplicate project(s) "
        + ("merged." if args.write else "found. Re-run with --write to persist.")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
