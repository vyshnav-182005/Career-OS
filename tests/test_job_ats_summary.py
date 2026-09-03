import unittest

from backend.services.ats_scoring import (
    build_job_ats_summaries,
    compute_quick_ats_match,
    extract_job_skill_terms,
    flatten_profile_skill_terms,
)

PROFILE = {
    "original_resume": {
        "skills": [{"category": "Languages", "skills": ["Python", "TypeScript", "SQL"]}],
        "projects": [{"name": "P", "technologies": ["FastAPI", "Docker"]}],
        "certifications": [],
        "languages": [],
    }
}

STRONG_FEATURES = {"semantic": 0.9, "family_fit": 1.0, "seniority_fit": 1.0}
WEAK_FEATURES = {"semantic": 0.2, "family_fit": 0.4, "seniority_fit": 0.5}


class ExtractJobSkillTermsTests(unittest.TestCase):
    def test_tagged_skills_are_preferred_and_canonicalized(self):
        terms = extract_job_skill_terms({"skills": ["python", "js"], "description": "irrelevant"})

        self.assertIn("Python", terms)
        self.assertIn("JavaScript", terms)

    def test_skills_are_mined_from_the_description_when_untagged(self):
        """Jooble never populates `skills`, so the JD text is the only signal."""
        job = {"skills": [], "description": "<p>You will write Python and TypeScript, plus some SQL.</p>"}

        terms = extract_job_skill_terms(job)

        self.assertIn("Python", terms)
        self.assertIn("TypeScript", terms)
        self.assertIn("SQL", terms)

    def test_mining_respects_word_boundaries(self):
        """'Go' must not fire on 'going'; that false positive skews the score."""
        terms = extract_job_skill_terms({"skills": [], "description": "You will be going to standups."})

        self.assertNotIn("Go", terms)

    def test_empty_job_yields_no_terms(self):
        self.assertEqual(extract_job_skill_terms({}), [])


class QuickAtsMatchTests(unittest.TestCase):
    def setUp(self):
        self.profile_terms = flatten_profile_skill_terms(PROFILE)

    def test_score_is_within_bounds(self):
        for job in ({}, {"skills": ["Python"]}, {"description": "Rust and Haskell only"}):
            for features in (STRONG_FEATURES, WEAK_FEATURES, {}):
                score = compute_quick_ats_match(self.profile_terms, job, features)
                self.assertGreaterEqual(score, 0)
                self.assertLessEqual(score, 100)

    def test_covered_skills_score_higher_than_missing_ones(self):
        covered = {"skills": ["Python", "TypeScript", "SQL", "Docker"]}
        missing = {"skills": ["Rust", "Haskell", "Scala", "Elixir"]}

        self.assertGreater(
            compute_quick_ats_match(self.profile_terms, covered, STRONG_FEATURES),
            compute_quick_ats_match(self.profile_terms, missing, STRONG_FEATURES),
        )

    def test_retrieval_features_move_the_score(self):
        job = {"skills": ["Python", "SQL", "Docker"]}

        self.assertGreater(
            compute_quick_ats_match(self.profile_terms, job, STRONG_FEATURES),
            compute_quick_ats_match(self.profile_terms, job, WEAK_FEATURES),
        )

    def test_thin_keyword_evidence_pulls_toward_neutral(self):
        """One incidental skill term must not swing the score to an extreme."""
        one_missing_skill = {"skills": ["Rust"]}

        score = compute_quick_ats_match(self.profile_terms, one_missing_skill, STRONG_FEATURES)

        self.assertGreater(score, 40)

    def test_scoring_is_deterministic(self):
        job = {"skills": ["Python", "Docker"]}
        scores = {compute_quick_ats_match(self.profile_terms, job, STRONG_FEATURES) for _ in range(5)}

        self.assertEqual(len(scores), 1)

    def test_malformed_feature_values_do_not_raise(self):
        score = compute_quick_ats_match(
            self.profile_terms, {"skills": ["Python"]}, {"semantic": None, "family_fit": "x"}
        )

        self.assertGreaterEqual(score, 0)


class BuildJobAtsSummariesTests(unittest.TestCase):
    def test_every_entry_gets_a_score_and_a_source(self):
        entries = [
            {"job": {"id": "a", "skills": ["Python"]}, "features": STRONG_FEATURES},
            {"job": {"id": "b", "skills": ["Rust"]}, "features": WEAK_FEATURES},
        ]

        result = build_job_ats_summaries(PROFILE, entries)

        for entry in result:
            self.assertIsInstance(entry["ats_match_score"], int)
            self.assertEqual(entry["ats_score_source"], "estimated")

    def test_a_cached_analysis_wins_over_the_estimate(self):
        entries = [{"job": {"id": "a", "skills": ["Rust"]}, "features": WEAK_FEATURES}]

        result = build_job_ats_summaries(PROFILE, entries, cached_scores={"a": {"overall_score": 87}})

        self.assertEqual(result[0]["ats_match_score"], 87)
        self.assertEqual(result[0]["ats_score_source"], "analyzed")

    def test_a_cached_row_without_a_score_falls_back_to_the_estimate(self):
        entries = [{"job": {"id": "a", "skills": ["Python"]}, "features": STRONG_FEATURES}]

        result = build_job_ats_summaries(PROFILE, entries, cached_scores={"a": {"suggestions": []}})

        self.assertEqual(result[0]["ats_score_source"], "estimated")

    def test_feature_scores_key_is_accepted_as_well_as_features(self):
        entries = [{"job": {"id": "a", "skills": ["Python"]}, "feature_scores": STRONG_FEATURES}]

        result = build_job_ats_summaries(PROFILE, entries)

        self.assertEqual(result[0]["ats_score_source"], "estimated")
        self.assertGreater(result[0]["ats_match_score"], 0)

    def test_entries_without_a_job_id_still_score(self):
        result = build_job_ats_summaries(PROFILE, [{"job": {"skills": ["Python"]}}])

        self.assertIn("ats_match_score", result[0])

    def test_empty_entry_list_is_handled(self):
        self.assertEqual(build_job_ats_summaries(PROFILE, []), [])


if __name__ == "__main__":
    unittest.main()
