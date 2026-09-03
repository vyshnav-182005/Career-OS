import unittest
from unittest.mock import patch

from backend.services import job_matching
from backend.services.job_matching import (
    _family_fit,
    _reciprocal_rank_fusion,
    _seniority_fit,
    _skill_overlap,
    retrieve_candidates,
)
from backend.models.profile import SearchIntent


def _job(job_id, title="Backend Engineer", company="Acme", role_family="backend",
         similarity=0.8, skills=None, posted_date="2024-01-01T00:00:00+00:00"):
    return {
        "id": job_id,
        "provider": "jooble",
        "provider_job_id": job_id,
        "title": title,
        "company": company,
        "role_family": role_family,
        "similarity": similarity,
        "skills": skills or [],
        "posted_date": posted_date,
    }


def _profile_data(search_intent=None):
    return {
        "original_resume": {},
        "preferred_job_roles": [],
        "strengths": [],
        "search_intent": search_intent,
    }


class ReciprocalRankFusionTests(unittest.TestCase):
    def test_orders_by_combined_rank_across_lists(self):
        list_a = [_job("j1"), _job("j2"), _job("j3")]
        list_b = [_job("j2"), _job("j3"), _job("j1")]

        scores = _reciprocal_rank_fusion([list_a, list_b])

        # j2 is rank1+rank2 across lists, j3 is rank2+rank2, j1 is rank1+rank3
        # -> j2 should score highest since it's top-ranked in one list and
        # second in the other.
        ranked = sorted(scores, key=scores.get, reverse=True)
        self.assertEqual(ranked[0], "j2")

    def test_job_present_in_only_one_list_still_scored(self):
        list_a = [_job("solo")]
        scores = _reciprocal_rank_fusion([list_a, []])
        self.assertIn("solo", scores)
        self.assertAlmostEqual(scores["solo"], 1.0 / (job_matching.RRF_K + 1))


class SkillOverlapTests(unittest.TestCase):
    def test_alias_collapsing_counts_as_a_match(self):
        # job lists the alias spelling, resume lists the canonical spelling -
        # canonicalize_skills should collapse both to "React" before comparing.
        overlap = _skill_overlap(job_skills=["reactjs"], resume_skills=["React"])
        self.assertEqual(overlap, 1.0)

    def test_no_overlap_scores_zero(self):
        overlap = _skill_overlap(job_skills=["Kubernetes"], resume_skills=["React"])
        self.assertEqual(overlap, 0.0)

    def test_empty_job_skills_scores_zero_not_divide_by_zero(self):
        overlap = _skill_overlap(job_skills=[], resume_skills=["React"])
        self.assertEqual(overlap, 0.0)

    def test_denominator_is_job_skill_count(self):
        # 1 of 2 job skills matched -> 0.5, per spec: |resume ∩ job| / max(1, |job skills|)
        overlap = _skill_overlap(job_skills=["React", "Kubernetes"], resume_skills=["React"])
        self.assertEqual(overlap, 0.5)


class FamilyFitTests(unittest.TestCase):
    def test_exact_family_scores_one(self):
        intent = SearchIntent(role_families=["backend"])
        self.assertEqual(_family_fit("backend", intent), 1.0)

    def test_adjacent_family_scores_point_six(self):
        intent = SearchIntent(role_families=["backend"])
        self.assertEqual(_family_fit("fullstack", intent), 0.6)

    def test_unrelated_family_is_hard_zero(self):
        intent = SearchIntent(role_families=["backend"])
        self.assertEqual(_family_fit("devops-sre", intent), 0.0)

    def test_excluded_family_is_hard_zero_even_if_also_adjacent(self):
        intent = SearchIntent(role_families=["backend"], excluded_families=["fullstack"])
        self.assertEqual(_family_fit("fullstack", intent), 0.0)

    def test_no_role_families_is_permissive_not_a_hard_drop(self):
        intent = SearchIntent()
        self.assertGreater(_family_fit("devops-sre", intent), 0.0)


class SeniorityFitTests(unittest.TestCase):
    def test_matching_seniority_scores_higher_than_mismatch(self):
        senior_intent = SearchIntent(seniority="senior")
        junior_intent = SearchIntent(seniority="junior")

        match_score = _seniority_fit("Senior Backend Engineer", senior_intent)
        mismatch_score = _seniority_fit("Senior Backend Engineer", junior_intent)

        self.assertGreater(match_score, mismatch_score)

    def test_title_without_seniority_signal_gets_neutral_default(self):
        intent = SearchIntent(seniority="mid")
        self.assertEqual(_seniority_fit("Backend Engineer", intent), 0.8)


class RetrieveCandidatesTests(unittest.TestCase):
    def _run(self, search_intent, vector_jobs, lexical_jobs=None, title_family_jobs=None):
        with patch.object(job_matching, "get_cached_profile_embedding", return_value=None), \
             patch.object(job_matching, "generate_profile_embedding", return_value=[0.1, 0.2, 0.3]), \
             patch.object(job_matching, "match_jobs_v2", return_value=vector_jobs), \
             patch.object(job_matching, "search_jobs_fulltext", return_value=lexical_jobs or []), \
             patch.object(job_matching, "get_jobs_by_role_family", return_value=title_family_jobs or []):
            return retrieve_candidates("user-1", _profile_data(search_intent))

    def test_excluded_family_job_never_appears_despite_high_similarity(self):
        search_intent = {"role_families": ["backend"], "excluded_families": ["devops-sre"]}
        jobs = [_job("devops-1", role_family="devops-sre", similarity=0.99)]

        results = self._run(search_intent, vector_jobs=jobs)

        self.assertEqual(results, [])

    def test_min_score_floor_drops_weak_match(self):
        # No family target, no skill overlap, old posting, no seniority signal,
        # low similarity - every feature is weak, so the weighted sum should
        # fall under MIN_SCORE even though nothing hard-drops it.
        search_intent = {"must_have_skills": ["Rust"]}
        jobs = [_job("weak-1", role_family=None, similarity=-0.9, skills=["COBOL"],
                      posted_date="2020-01-01T00:00:00+00:00")]

        results = self._run(search_intent, vector_jobs=jobs)

        self.assertEqual(results, [])

    def test_search_intent_none_falls_back_to_permissive_defaults(self):
        jobs = [_job("any-1", role_family="devops-sre", similarity=0.9)]

        results = self._run(None, vector_jobs=jobs)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].job.id, "any-1")

    def test_strong_match_survives_and_carries_retrieval_source(self):
        search_intent = {"role_families": ["backend"], "must_have_skills": ["Python"]}
        jobs = [_job("strong-1", role_family="backend", similarity=0.9, skills=["Python"])]

        results = self._run(search_intent, vector_jobs=jobs)

        self.assertEqual(len(results), 1)
        self.assertIn("vector", results[0].retrieval_sources)
        self.assertEqual(results[0].features.family_fit, 1.0)

    def test_embedding_unavailable_returns_none_not_empty_list(self):
        with patch.object(job_matching, "get_cached_profile_embedding", return_value=None), \
             patch.object(job_matching, "generate_profile_embedding", return_value=[]):
            result = retrieve_candidates("user-1", _profile_data())

        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
