"""
run_pipeline.py — Standalone CLI entry point for the resume-to-profile pipeline.

Spawned as a subprocess by the Next.js backend.

Usage:
    python run_pipeline.py <file_path> <content_type> <user_id>

Output:
    Prints JSON to stdout:
      - On success: {"success": true, "parsed_resume": {...}, "profile_intelligence": {...}}
      - On error:   {"success": false, "error": "..."}

All logging goes to stderr so it never corrupts the JSON on stdout.
"""

import json
import logging
import os
import sys

# ── Configure logging to stderr BEFORE any app imports ───────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)


def main() -> None:
    if len(sys.argv) != 4:
        result = {
            "success": False,
            "error": "Usage: python run_pipeline.py <file_path> <content_type> <user_id>",
        }
        print(json.dumps(result))
        sys.exit(1)

    file_path = sys.argv[1]
    content_type = sys.argv[2]
    user_id = sys.argv[3]

    filename = os.path.basename(file_path)

    try:
        # 1. Read file bytes from disk
        logger.info("Reading file: %s", file_path)
        with open(file_path, "rb") as f:
            file_bytes = f.read()
        logger.info("Read %d bytes from %s", len(file_bytes), filename)

        # 2. Parse resume
        from app.parser import parse_resume

        logger.info("Parsing resume (content_type=%s)", content_type)
        parsed_resume = parse_resume(file_bytes, content_type)
        logger.info("Resume parsed successfully")

        # 3. Analyze profile
        from app.profile_agent import analyze_profile

        logger.info("Running profile intelligence analysis")
        profile_intelligence = analyze_profile(parsed_resume)
        logger.info("Profile analysis complete")

        # 4. Persist to Supabase
        from app.supabase_client import upsert_profile

        logger.info("Upserting profile to Supabase for user_id=%s", user_id)
        upsert_profile(user_id, profile_intelligence, source_filename=filename)
        logger.info("Profile persisted successfully")

        # 5. Print result JSON to stdout
        result = {
            "success": True,
            "parsed_resume": parsed_resume.model_dump(),
            "profile_intelligence": profile_intelligence.model_dump(),
        }
        print(json.dumps(result, default=str))

    except Exception as e:
        logger.exception("Pipeline failed: %s", e)
        result = {
            "success": False,
            "error": str(e),
        }
        print(json.dumps(result, default=str))
        sys.exit(1)


if __name__ == "__main__":
    main()
