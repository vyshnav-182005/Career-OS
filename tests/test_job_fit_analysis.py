import unittest
from unittest.mock import AsyncMock, patch

from backend.models.resume import ParsedResume, Project
from backend.models.schemas import ATSScore
from backend.services import job_fit_analysis as jfa


PROFILE_DATA = {
    "original_resume": {
        "projects": [
            {"name": "Inventory Tracker", "technologies": ["Flask"], "description": ["Built the API"]}
        ],
        "skills": [{"category": "Languages", "skills": ["Python"]}],
    },
    "strengths": [],
    "preferred_job_roles": [],
}

JOB_ROW = {"id": "job-1", "title": "Backend Engineer", "description": "Build APIs.", "skills": ["Python"]}

SAMPLE_ATS_SCORE = ATSScore(
    overall_score=80,
    skill_match_pct=100,
    project_relevance_score=80,
    experience_relevance_score=80,
    education_match_score=80,
)


class AnalyzeJobFitTests(unittest.IsolatedAsyncioTestCase):
    def _patch_common(self, *, cached=None, profile_updated_at="2020-01-01T00:00:00Z"):
        return [
            patch.object(jfa, "get_job_by_id", return_value=JOB_ROW),
            patch.object(jfa, "get_profile_data", return_value=PROFILE_DATA),
            patch.object(jfa, "get_job_fit_analysis", return_value=cached),
            patch.object(jfa, "get_profile_updated_at", return_value=profile_updated_at),
            patch.object(jfa, "upsert_optimized_resume_snapshot"),
            patch.object(jfa, "upsert_ats_score"),
        ]

    async def test_raises_job_not_found(self):
        with patch.object(jfa, "get_job_by_id", return_value=None):
            with self.assertRaises(jfa.JobNotFoundError):
                await jfa.analyze_job_fit("user-1", "missing-job")

    async def test_raises_profile_not_found(self):
        with patch.object(jfa, "get_job_by_id", return_value=JOB_ROW), \
             patch.object(jfa, "get_profile_data", return_value=None):
            with self.assertRaises(jfa.ProfileNotFoundError):
                await jfa.analyze_job_fit("user-1", "job-1")

    async def test_computes_fresh_analysis_when_no_cache(self):
        patches = self._patch_common(cached=None)
        with patches[0], patches[1], patches[2], patches[3], patches[4] as mock_snapshot, patches[5] as mock_ats, \
             patch.object(jfa, "run_resume_optimization", new_callable=AsyncMock) as mock_run, \
             patch.object(jfa, "compute_ats_score", new_callable=AsyncMock) as mock_score:
            mock_run.return_value = ParsedResume(
                projects=[Project(name="Inventory Tracker", technologies=["Flask"], description=["Built the API well"])]
            )
            mock_score.return_value = SAMPLE_ATS_SCORE

            result = await jfa.analyze_job_fit("user-1", "job-1")

        mock_run.assert_awaited_once()
        mock_score.assert_awaited_once()
        mock_snapshot.assert_called_once()
        mock_ats.assert_called_once()
        self.assertTrue(result.success)
        self.assertEqual(result.ats_score.overall_score, 80)
        self.assertEqual(len(result.optimized_projects), 1)

    async def test_reuses_fresh_cache_without_calling_llm(self):
        cached_resume = ParsedResume(
            projects=[Project(name="Inventory Tracker", technologies=["Flask"], description=["Built the API well"])]
        )
        cached = {
            "optimized_resume_json": cached_resume.model_dump(),
            "optimized_projects": [],
            "ats_score": SAMPLE_ATS_SCORE.model_dump(),
            "updated_at": "2025-01-01T00:00:00Z",
        }
        patches = self._patch_common(cached=cached, profile_updated_at="2020-01-01T00:00:00Z")
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], \
             patch.object(jfa, "run_resume_optimization", new_callable=AsyncMock) as mock_run, \
             patch.object(jfa, "compute_ats_score", new_callable=AsyncMock) as mock_score:
            result = await jfa.analyze_job_fit("user-1", "job-1")

        mock_run.assert_not_awaited()
        mock_score.assert_not_awaited()
        self.assertTrue(result.success)
        self.assertEqual(result.ats_score.overall_score, 80)

    async def test_stale_cache_triggers_recompute(self):
        cached_resume = ParsedResume(projects=[])
        cached = {
            "optimized_resume_json": cached_resume.model_dump(),
            "ats_score": SAMPLE_ATS_SCORE.model_dump(),
            "updated_at": "2020-01-01T00:00:00Z",
        }
        # Profile was updated AFTER the cached analysis -> must not be reused
        patches = self._patch_common(cached=cached, profile_updated_at="2025-06-01T00:00:00Z")
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], \
             patch.object(jfa, "run_resume_optimization", new_callable=AsyncMock) as mock_run, \
             patch.object(jfa, "compute_ats_score", new_callable=AsyncMock) as mock_score:
            mock_run.return_value = ParsedResume(projects=[])
            mock_score.return_value = SAMPLE_ATS_SCORE

            await jfa.analyze_job_fit("user-1", "job-1")

        mock_run.assert_awaited_once()
        mock_score.assert_awaited_once()

    async def test_force_refresh_ignores_fresh_cache(self):
        cached_resume = ParsedResume(projects=[])
        cached = {
            "optimized_resume_json": cached_resume.model_dump(),
            "ats_score": SAMPLE_ATS_SCORE.model_dump(),
            "updated_at": "2025-01-01T00:00:00Z",
        }
        with patch.object(jfa, "get_job_by_id", return_value=JOB_ROW), \
             patch.object(jfa, "get_profile_data", return_value=PROFILE_DATA), \
             patch.object(jfa, "get_job_fit_analysis", return_value=cached) as mock_get_cached, \
             patch.object(jfa, "get_profile_updated_at", return_value="2020-01-01T00:00:00Z"), \
             patch.object(jfa, "upsert_optimized_resume_snapshot"), \
             patch.object(jfa, "upsert_ats_score"), \
             patch.object(jfa, "run_resume_optimization", new_callable=AsyncMock) as mock_run, \
             patch.object(jfa, "compute_ats_score", new_callable=AsyncMock) as mock_score:
            mock_run.return_value = ParsedResume(projects=[])
            mock_score.return_value = SAMPLE_ATS_SCORE

            await jfa.analyze_job_fit("user-1", "job-1", force_refresh=True)

        mock_get_cached.assert_not_called()
        mock_run.assert_awaited_once()
        mock_score.assert_awaited_once()

    async def test_returns_failure_when_resume_optimization_fails(self):
        patches = self._patch_common(cached=None)
        # compute_ats_score is patched for the same reason as in the tests above:
        # left unpatched it issues a real LLM request, which makes this a network
        # test rather than a unit test of the optimization-failure path.
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], \
             patch.object(jfa, "run_resume_optimization", new_callable=AsyncMock) as mock_run, \
             patch.object(jfa, "compute_ats_score", new_callable=AsyncMock) as mock_score:
            mock_run.return_value = None
            mock_score.return_value = None

            result = await jfa.analyze_job_fit("user-1", "job-1")

        self.assertFalse(result.success)


if __name__ == "__main__":
    unittest.main()
