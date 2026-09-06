import unittest
from unittest.mock import AsyncMock, Mock, patch

from backend.agents import job_matching_agent
from backend.agents.job_matching_agent import RankedJob, rank_jobs, select_top_matches
from backend.models.job import MatchedJob
from backend.services.job_matching import ScoredFeatures, ScoredJob


def _scored_job(job_id, title="Backend Engineer", skills=None, score=0.7):
    job = MatchedJob(
        id=job_id,
        provider="jooble",
        provider_job_id=job_id,
        title=title,
        company="Acme",
        description="Build and ship backend services.",
        skills=skills or ["Python"],
    )
    features = ScoredFeatures(
        semantic=0.8, skill_overlap=0.5, family_fit=1.0, seniority_fit=0.8, recency=0.9
    )
    return ScoredJob(job=job, features=features, score=score, retrieval_sources=["vector"])


def _ranked(job_id, verdict, score):
    return RankedJob(
        job=MatchedJob(id=job_id, provider="jooble", provider_job_id=job_id, title="X", company="Y"),
        features=ScoredFeatures(semantic=0.5, skill_overlap=0.5, family_fit=1.0, seniority_fit=0.5, recency=0.5),
        verdict=verdict,
        score=score,
        reason="",
        matched_skills=[],
        missing_skills=[],
        retrieval_sources=[],
    )


class RankJobsCacheHitTests(unittest.IsolatedAsyncioTestCase):
    async def test_cache_hit_returns_cached_verdict_without_calling_llm(self):
        cached_row = {
            "job_id": "job-1",
            "verdict": "strong",
            "score": 88,
            "reason": "Great fit.",
            "matched_skills": ["Python"],
            "missing_skills": [],
        }
        llm_mock = AsyncMock()
        with patch.object(job_matching_agent, "get_profile_version", return_value="v1"), \
             patch.object(job_matching_agent, "get_cached_job_matches", return_value={"job-1": cached_row}), \
             patch.object(job_matching_agent, "_call_llm", llm_mock), \
             patch.object(job_matching_agent, "upsert_job_matches") as upsert_mock:
            result = await rank_jobs("user-1", [_scored_job("job-1")], profile_data={})

        llm_mock.assert_not_called()
        upsert_mock.assert_not_called()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].verdict, "strong")
        self.assertEqual(result[0].score, 88)
        self.assertEqual(result[0].matched_skills, ["Python"])


class RankJobsCacheMissTests(unittest.IsolatedAsyncioTestCase):
    async def test_cache_miss_calls_llm_once_and_persists_result(self):
        llm_response = (
            '{"results": [{"index": 0, "verdict": "possible", "score": 60, '
            '"reason": "Missing one framework.", "matched_skills": ["Python"], '
            '"missing_skills": ["Go"]}]}'
        )
        llm_mock = AsyncMock(return_value=llm_response)
        with patch.object(job_matching_agent, "get_profile_version", return_value="v1"), \
             patch.object(job_matching_agent, "get_cached_job_matches", return_value={}), \
             patch.object(job_matching_agent, "_call_llm", llm_mock), \
             patch.object(job_matching_agent, "upsert_job_matches") as upsert_mock:
            result = await rank_jobs("user-1", [_scored_job("job-1")], profile_data={})

        llm_mock.assert_called_once()
        upsert_mock.assert_called_once()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].verdict, "possible")
        self.assertEqual(result[0].score, 60)
        self.assertEqual(result[0].missing_skills, ["Go"])


class HallucinatedMissingSkillTests(unittest.IsolatedAsyncioTestCase):
    async def test_missing_skill_the_candidate_actually_has_is_dropped(self):
        # The LLM claims "Node.js" is missing, but it's literally in the
        # candidate's own must_have_skills - this is the exact live failure
        # mode observed (cross-job attribution errors), and must never reach
        # the response even though the LLM's own JSON was well-formed.
        llm_response = (
            '{"results": [{"index": 0, "verdict": "reject", "score": 20, '
            '"reason": "Lacks Node.js experience.", "matched_skills": [], '
            '"missing_skills": ["Node.js", "Go"]}]}'
        )
        llm_mock = AsyncMock(return_value=llm_response)
        profile_data = {"search_intent": {"must_have_skills": ["Node.js"], "nice_to_have_skills": []}}
        with patch.object(job_matching_agent, "get_profile_version", return_value="v1"), \
             patch.object(job_matching_agent, "get_cached_job_matches", return_value={}), \
             patch.object(job_matching_agent, "_call_llm", llm_mock), \
             patch.object(job_matching_agent, "upsert_job_matches"):
            result = await rank_jobs("user-1", [_scored_job("job-1")], profile_data=profile_data)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].missing_skills, ["Go"])
        self.assertNotIn("Node.js", result[0].missing_skills)
        # The verdict/reason are left as the LLM gave them - only the
        # structured missing_skills list is corrected.
        self.assertEqual(result[0].verdict, "reject")


class RankJobsMalformedResponseTests(unittest.IsolatedAsyncioTestCase):
    async def test_malformed_response_falls_back_to_feature_ranking(self):
        llm_mock = AsyncMock(return_value="not valid json at all")
        with patch.object(job_matching_agent, "get_profile_version", return_value="v1"), \
             patch.object(job_matching_agent, "get_cached_job_matches", return_value={}), \
             patch.object(job_matching_agent, "_call_llm", llm_mock), \
             patch.object(job_matching_agent, "upsert_job_matches") as upsert_mock:
            result = await rank_jobs("user-1", [_scored_job("job-1", score=0.7)], profile_data={})

        self.assertEqual(len(result), 1)
        # Fallback never rejects a job retrieval already deemed a real candidate.
        self.assertIn(result[0].verdict, {"strong", "possible"})
        self.assertIn("AI reviewer was unavailable", result[0].reason)
        # A fallback must NOT be cached. The cache is keyed on profile_version and
        # is consulted before the LLM, so a persisted fallback is served back on
        # every later request and blocks the retry that would replace it - which
        # is how a transient provider outage turned into permanently degraded
        # results. Leaving the miss uncached lets the next request heal it.
        upsert_mock.assert_not_called()

    async def test_real_llm_verdict_is_persisted(self):
        """The flip side of the test above: a genuine verdict is still cached,
        so the LLM is not re-run for the same job on the next request."""
        llm_mock = AsyncMock(return_value=(
            '{"results": [{"index": 0, "verdict": "strong", "score": 91, '
            '"reason": "Strong backend overlap.", "matched_skills": ["Python"], '
            '"missing_skills": []}]}'
        ))
        with patch.object(job_matching_agent, "get_profile_version", return_value="v1"),              patch.object(job_matching_agent, "get_cached_job_matches", return_value={}),              patch.object(job_matching_agent, "_call_llm", llm_mock),              patch.object(job_matching_agent, "upsert_job_matches") as upsert_mock:
            result = await rank_jobs("user-1", [_scored_job("job-1")], profile_data={})

        self.assertEqual(result[0].verdict, "strong")
        self.assertEqual(result[0].score, 91)
        upsert_mock.assert_called_once()
        persisted = upsert_mock.call_args[0][0]
        self.assertEqual(len(persisted), 1)
        self.assertEqual(persisted[0]["job_id"], "job-1")
        self.assertEqual(persisted[0]["verdict"], "strong")

    async def test_result_count_mismatch_is_treated_as_malformed(self):
        llm_mock = AsyncMock(return_value='{"results": []}')
        with patch.object(job_matching_agent, "get_profile_version", return_value="v1"), \
             patch.object(job_matching_agent, "get_cached_job_matches", return_value={}), \
             patch.object(job_matching_agent, "_call_llm", llm_mock), \
             patch.object(job_matching_agent, "upsert_job_matches"):
            result = await rank_jobs("user-1", [_scored_job("job-1")], profile_data={})

        self.assertEqual(len(result), 1)
        self.assertIn(result[0].verdict, {"strong", "possible"})


class SelectTopMatchesTests(unittest.TestCase):
    def test_reject_verdicts_are_dropped(self):
        ranked = [_ranked("j1", "reject", 95), _ranked("j2", "strong", 80)]
        result = select_top_matches(ranked)
        self.assertEqual([rj.job.id for rj in result], ["j2"])

    def test_survivors_sorted_by_score_descending(self):
        ranked = [_ranked("j1", "possible", 40), _ranked("j2", "strong", 90), _ranked("j3", "strong", 70)]
        result = select_top_matches(ranked)
        self.assertEqual([rj.job.id for rj in result], ["j2", "j3", "j1"])

    def test_top_n_caps_result_count(self):
        ranked = [_ranked(f"j{i}", "strong", i) for i in range(15)]
        result = select_top_matches(ranked, top_n=10)
        self.assertEqual(len(result), 10)


if __name__ == "__main__":
    unittest.main()
