#!/usr/bin/env python3
"""
Checks every board token in backend/data/ats_companies.json against the live
ATS API and reports which ones actually resolve.

Company job boards move: a company migrates from Lever to Greenhouse, renames
its board, or gets acquired, and the token in the seed file quietly stops
working. The providers already treat a dead token as a fetch failure (which
suppresses expiration, so nothing gets wrongly deleted) - but a seed file full
of 404s means no board is ever considered "complete" and expiration never runs.
This script is how you clean it up.

    python scripts/verify_ats_boards.py            # report only
    python scripts/verify_ats_boards.py --prune    # rewrite the file, dead tokens removed
    python scripts/verify_ats_boards.py --vendor lever
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.services.job_providers.ats_base import SEED_FILE  # noqa: E402

VENDOR_URLS = {
    "greenhouse": "https://boards-api.greenhouse.io/v1/boards/{token}/jobs",
    "lever": "https://api.lever.co/v0/postings/{token}?mode=json",
}

HEADERS = {"User-Agent": "CareerOS/1.0 (board verification)", "Accept": "application/json"}


def check(vendor: str, entry: dict) -> tuple[dict, bool, str]:
    token = entry.get("token", "")
    url = VENDOR_URLS[vendor].format(token=token)
    try:
        response = requests.get(url, headers=HEADERS, timeout=20)
    except requests.RequestException as exc:
        return entry, False, f"unreachable ({type(exc).__name__})"

    if response.status_code == 404:
        return entry, False, "404 - no such board"
    if not response.ok:
        return entry, False, f"HTTP {response.status_code}"

    try:
        payload = response.json()
    except ValueError:
        return entry, False, "non-JSON response"

    count = len(payload.get("jobs", [])) if isinstance(payload, dict) else len(payload)
    if count == 0:
        # Resolves but is empty: usually a real board with no open roles right
        # now. Kept, since it will fill back up.
        return entry, True, "ok - 0 open roles"
    return entry, True, f"ok - {count} jobs"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--prune", action="store_true", help="rewrite the seed file without the dead tokens")
    parser.add_argument("--vendor", choices=sorted(VENDOR_URLS), help="check only one vendor")
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()

    with open(SEED_FILE, "r", encoding="utf-8") as handle:
        data = json.load(handle)

    vendors = [args.vendor] if args.vendor else [v for v in VENDOR_URLS if v in data]
    total_ok = total_dead = 0

    for vendor in vendors:
        entries = data.get(vendor, [])
        print(f"\n=== {vendor} ({len(entries)} boards) ===")

        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            results = list(pool.map(lambda entry: check(vendor, entry), entries))

        alive = []
        for entry, ok, detail in results:
            mark = "PASS" if ok else "FAIL"
            print(f"  [{mark}] {entry.get('name', ''):<20} {entry.get('token', ''):<16} {detail}")
            if ok:
                alive.append(entry)
                total_ok += 1
            else:
                total_dead += 1

        if args.prune:
            data[vendor] = alive

    print(f"\n{total_ok} live, {total_dead} dead.")

    if args.prune:
        with open(SEED_FILE, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        print(f"Pruned {SEED_FILE}.")
    elif total_dead:
        print("Re-run with --prune to remove the dead tokens.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
