import unittest
from unittest.mock import patch

from fastapi import BackgroundTasks

from backend.routers import jobs as jobs_router


def _job(job_id: str, title: str = "Backend Engineer") -> dict:
    return {
        "id": job_id,
        "title": title,
        "company": "Acme",
        "description": "Python, PostgreSQL, Docker.",
        "skills": ["Python"],
        "provider": "greenhouse",
        "provider_job_id": f"acme:{job_id}",
    }


PROFILE = {"original_resume": {"skills": [{"skills": ["Python", "Docker"]}]}}


class JobSearchEndpointTests(unittest.TestCase):
    def setUp(self):
        # The endpoint debounces ingestion per search term in module state,
        # which would otherwise leak between tests.
        jobs_router._last_query_ingestion.clear()

    def _call(self, q="backend", limit=20, candidates=None, profile=PROFILE, scores=None):
        candidates = candidates if candidates is not None else [_job("a"), _job("b")]
        background = BackgroundTasks()

        with patch.object(jobs_router, "get_jobs_by_filter", return_value=candidates) as mock_filter, \
             patch.object(jobs_router, "get_profile_data", return_value=profile), \
             patch.object(jobs_router, "get_ats_scores_for_jobs", return_value=scores or {}):
            response = jobs_router.search_jobs(
                user_id="u1", background_tasks=background, q=q, limit=limit
            )

        return response, background, mock_filter

    def test_returns_recommended_entry_shape(self):
        response, _, _ = self._call()

        self.assertTrue(response["success"])
        entry = response["data"][0]
        # Same shape as /jobs/recommended so the UI has one card renderer.
        self.assertIn("job", entry)
        self.assertIn("ats_match_score", entry)
        self.assertIn("ats_score_source", entry)

    def test_results_ordered_by_match_score_not_recency(self):
        candidates = [_job("weak", "Marketing Manager"), _job("strong", "Backend Engineer")]

        response, _, _ = self._call(candidates=candidates)

        scores = [entry["ats_match_score"] for entry in response["data"]]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_candidate_pool_is_wider_than_the_returned_limit(self):
        # Scoring only the rows we intend to return would make the ranking
        # meaningless - the DB orders by posted_date, not by fit.
        _, _, mock_filter = self._call(limit=5)

        self.assertGreaterEqual(
            mock_filter.call_args.kwargs["limit"], jobs_router.SEARCH_CANDIDATE_POOL
        )

    def test_limit_truncates_the_response(self):
        response, _, _ = self._call(limit=1, candidates=[_job("a"), _job("b"), _job("c")])

        self.assertEqual(len(response["data"]), 1)

    def test_search_schedules_background_ingestion_for_the_term(self):
        _, background, _ = self._call(q="data scientist")

        self.assertEqual(len(background.tasks), 1)

    def test_empty_query_does_not_schedule_ingestion(self):
        # An empty box shows the newest stored jobs; there's no term to fetch.
        _, background, _ = self._call(q="")

        self.assertEqual(len(background.tasks), 0)

    def test_missing_profile_still_returns_jobs(self):
        response, _, _ = self._call(profile=None)

        self.assertTrue(response["success"])
        self.assertEqual(len(response["data"]), 2)
        self.assertIsNone(response["data"][0].get("ats_match_score"))

    def test_analyzed_score_beats_the_estimate(self):
        response, _, _ = self._call(
            candidates=[_job("a")], scores={"a": {"overall_score": 91}}
        )

        entry = response["data"][0]
        self.assertEqual(entry["ats_match_score"], 91)
        self.assertEqual(entry["ats_score_source"], "analyzed")


class QueryIngestionDebounceTests(unittest.TestCase):
    def setUp(self):
        jobs_router._last_query_ingestion.clear()

    def test_same_term_only_fans_out_once_within_the_window(self):
        with patch.object(jobs_router, "JobIngestionWorkflow") as mock_workflow:
            jobs_router._background_ingest_for_query("backend engineer")
            jobs_router._background_ingest_for_query("Backend Engineer")  # case-insensitive

        self.assertEqual(mock_workflow.call_count, 1)

    def test_blank_term_is_ignored(self):
        with patch.object(jobs_router, "JobIngestionWorkflow") as mock_workflow:
            jobs_router._background_ingest_for_query("   ")

        mock_workflow.assert_not_called()


if __name__ == "__main__":
    unittest.main()
