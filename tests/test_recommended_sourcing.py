import unittest
from unittest.mock import AsyncMock, patch

from fastapi import BackgroundTasks

from backend.routers import jobs as jobs_router

PROFILE = {
    "original_resume": {"skills": [{"skills": ["Verilog"]}]},
    "preferred_job_roles": [{"title": "RF Engineering Intern"}],
    "search_intent": {"role_families": ["hardware-electronics"]},
}


class RecommendedSourcingFlagTests(unittest.IsolatedAsyncioTestCase):
    """
    /jobs/recommended queues ingestion for the profile's roles as a background
    task, which by definition runs after the response is sent. So the first
    candidate from a field with no stored jobs gets an empty list even though
    their jobs are being fetched right then. The response says so, letting the
    client show "sourcing" and come back, instead of a dead empty state.
    """

    def setUp(self):
        jobs_router._last_ingestion_trigger.clear()

    async def _call(self, scored, ranked=None):
        background = BackgroundTasks()
        with patch.object(jobs_router, "get_profile_data", return_value=PROFILE), \
             patch.object(jobs_router, "retrieve_candidates", return_value=scored), \
             patch.object(jobs_router, "rank_jobs", AsyncMock(return_value=ranked or [])), \
             patch.object(jobs_router, "select_top_matches", return_value=ranked or []), \
             patch.object(jobs_router, "build_job_ats_summaries", side_effect=lambda p, e, **k: e), \
             patch.object(jobs_router, "get_ats_scores_for_jobs", return_value={}):
            return await jobs_router.get_recommended_jobs(
                user_id="u1", background_tasks=background, legacy=False, limit=10
            )

    async def test_empty_result_is_reported_as_sourcing(self):
        response = await self._call(scored=[])
        self.assertTrue(response["success"])
        self.assertEqual(response["data"], [])
        self.assertTrue(response["sourcing"])

    async def test_results_are_not_reported_as_sourcing(self):
        ranked = [type("R", (), {"model_dump": lambda self: {"job": {"id": "j1"}}})()]
        response = await self._call(scored=["candidate"], ranked=ranked)
        self.assertTrue(response["success"])
        self.assertEqual(len(response["data"]), 1)
        self.assertFalse(response["sourcing"])

    async def test_embedding_failure_is_not_reported_as_sourcing(self):
        """
        retrieve_candidates returns None only when the embedding is genuinely
        unavailable. That is an error state, not "we are fetching your jobs",
        and must keep its own distinct response.
        """
        response = await self._call(scored=None)
        self.assertFalse(response["success"])
        self.assertEqual(response["error"], "embedding_unavailable")
        self.assertNotIn("sourcing", response)


if __name__ == "__main__":
    unittest.main()
