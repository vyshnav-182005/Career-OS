"""
get_cached_job_matches has to treat the two kinds of cached row differently.

A real LLM verdict is valid until the profile it was computed against changes,
which is what profile_version already encodes. A feature-ranking fallback is
the record of an LLM call that did not happen, so serving it under the same
rule pins "the AI reviewer was unavailable" to that job until the user next
edits their profile. Refusing to store fallbacks at all - the previous
behaviour - swapped that for a latency problem: with nothing cached, every
subsequent request re-ran the entire LLM fan-out for those jobs.

So fallbacks are stored and aged out. These tests pin that boundary.
"""

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from backend.db import supabase_client
from backend.db.supabase_client import FALLBACK_CACHE_TTL_SECONDS, get_cached_job_matches


def _row(job_id: str, from_llm: bool, age_seconds: float) -> dict:
    updated = datetime.now(timezone.utc) - timedelta(seconds=age_seconds)
    return {
        "job_id": job_id,
        "verdict": "possible",
        "score": 70,
        "reason": "why",
        "matched_skills": [],
        "missing_skills": [],
        "from_llm": from_llm,
        "updated_at": updated.isoformat(),
    }


class GetCachedJobMatchesTests(unittest.TestCase):
    def _fetch(self, rows, job_ids=("job-1",)):
        client = MagicMock()
        client.table.return_value.select.return_value.eq.return_value.eq.return_value.in_.return_value.execute.return_value = MagicMock(
            data=rows
        )
        with patch.object(supabase_client, "get_supabase_client", return_value=client):
            return get_cached_job_matches("user-1", list(job_ids), "v1")

    def test_real_verdict_is_served_however_old(self):
        # Age is irrelevant for a genuine verdict: profile_version is what
        # invalidates it, and an unchanged profile means it is still correct.
        result = self._fetch([_row("job-1", from_llm=True, age_seconds=90 * 24 * 3600)])
        self.assertIn("job-1", result)

    def test_recent_fallback_is_served(self):
        # Inside the window the fallback stands in for the LLM, which is what
        # stops a page refresh from re-firing the whole fan-out.
        result = self._fetch([_row("job-1", from_llm=False, age_seconds=FALLBACK_CACHE_TTL_SECONDS / 2)])
        self.assertIn("job-1", result)

    def test_expired_fallback_is_dropped_so_the_llm_is_retried(self):
        result = self._fetch([_row("job-1", from_llm=False, age_seconds=FALLBACK_CACHE_TTL_SECONDS + 60)])
        self.assertEqual(result, {})

    def test_row_without_from_llm_column_is_treated_as_a_real_verdict(self):
        # Rows written before the column existed, and any read taken against a
        # database where the migration has not been applied yet. Only real
        # verdicts were ever persisted then, so that is the accurate reading.
        legacy = _row("job-1", from_llm=True, age_seconds=10 * 24 * 3600)
        del legacy["from_llm"]
        self.assertIn("job-1", self._fetch([legacy]))

    def test_unparseable_timestamp_expires_a_fallback(self):
        # Failing closed: a fallback we cannot date is retried rather than
        # served forever on the strength of a malformed value.
        row = _row("job-1", from_llm=False, age_seconds=0)
        row["updated_at"] = "not a timestamp"
        self.assertEqual(self._fetch([row]), {})

    def test_mixed_rows_keep_only_what_is_still_valid(self):
        rows = [
            _row("job-1", from_llm=True, age_seconds=99999),
            _row("job-2", from_llm=False, age_seconds=5),
            _row("job-3", from_llm=False, age_seconds=FALLBACK_CACHE_TTL_SECONDS + 1),
        ]
        result = self._fetch(rows, job_ids=("job-1", "job-2", "job-3"))
        self.assertEqual(sorted(result), ["job-1", "job-2"])

    def test_no_profile_version_means_no_cache(self):
        # Without a version there is nothing to scope a verdict to, so the
        # caller must go to the LLM rather than risk serving another
        # profile's results.
        self.assertEqual(get_cached_job_matches("user-1", ["job-1"], None), {})


if __name__ == "__main__":
    unittest.main()
