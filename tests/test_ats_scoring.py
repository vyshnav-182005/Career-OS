import unittest

from backend.models.resume import Experience, Project
from backend.models.schemas import ATSScore
from backend.services.ats_scoring import (
    compute_overall_score,
    compute_skill_coverage,
    extract_optimized_projects,
    flatten_profile_skill_terms,
    flatten_resume_skill_terms,
    log_optimization_skill_delta,
    verify_bullet_grounding,
    verify_experience_grounding,
)


class SkillCoverageTests(unittest.TestCase):
    def test_exact_and_fuzzy_matches_are_covered(self):
        profile_terms = {"python", "react.js", "postgresql"}

        result = compute_skill_coverage(
            required=["Python", "React"],
            preferred=["Docker"],
            profile_terms=profile_terms,
        )

        self.assertEqual(result["required_skills_covered"], ["Python", "React"])
        self.assertEqual(result["required_skills_missing"], [])
        self.assertEqual(result["preferred_skills_missing"], ["Docker"])
        self.assertEqual(result["skill_match_pct"], round(2 / 3 * 100))

    def test_empty_skill_lists_default_to_full_coverage(self):
        result = compute_skill_coverage(required=[], preferred=[], profile_terms={"python"})
        self.assertEqual(result["skill_match_pct"], 100)


class OverallScoreTests(unittest.TestCase):
    def test_weighted_average_is_clamped_to_0_100(self):
        score = compute_overall_score(
            skill_match_pct=100,
            project_relevance_score=100,
            experience_relevance_score=100,
            education_match_score=100,
        )
        self.assertEqual(score, 100)

        score = compute_overall_score(0, 0, 0, 0)
        self.assertEqual(score, 0)

    def test_skills_are_weighted_highest(self):
        high_skill = compute_overall_score(100, 0, 0, 0)
        high_education = compute_overall_score(0, 0, 0, 100)
        self.assertGreater(high_skill, high_education)


class BulletGroundingTests(unittest.TestCase):
    def setUp(self):
        self.original_bullets = [
            "Built a REST API using Flask and PostgreSQL for inventory tracking",
        ]
        self.technologies = ["Flask", "PostgreSQL"]

    def test_rephrased_bullet_is_grounded(self):
        bullet = "Developed a REST API leveraging Flask and PostgreSQL to manage inventory tracking"
        self.assertTrue(verify_bullet_grounding(bullet, self.original_bullets, self.technologies))

    def test_fabricated_bullet_is_rejected(self):
        bullet = "Led a team of 12 engineers to migrate infrastructure to Kubernetes, cutting costs by 40%"
        self.assertFalse(verify_bullet_grounding(bullet, self.original_bullets, self.technologies))

    def test_empty_bullet_is_rejected(self):
        self.assertFalse(verify_bullet_grounding("", self.original_bullets, self.technologies))


class ExtractOptimizedProjectsTests(unittest.TestCase):
    def test_pairs_by_name_caps_bullets_and_falls_back_ungrounded_bullets(self):
        original_projects = [
            {
                "name": "Inventory Tracker",
                "technologies": ["Flask", "PostgreSQL"],
                "description": [
                    "Built a REST API using Flask and PostgreSQL for inventory tracking",
                    "Wrote integration tests with pytest covering core endpoints",
                    "Deployed the service to a Linux VM using Docker",
                ],
            }
        ]
        optimized = [
            Project(
                name="Inventory Tracker",
                technologies=["Flask", "PostgreSQL"],
                description=[
                    "Engineered a Flask/PostgreSQL REST API to track inventory in real time",
                    "Led a team of 12 engineers to migrate to Kubernetes",  # fabricated -> should fall back
                ],
            )
        ]

        result = extract_optimized_projects(original_projects, optimized)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].project_name, "Inventory Tracker")
        self.assertEqual(len(result[0].optimized_bullets), 2)
        # Second bullet was ungrounded -> replaced with the original bullet at that position
        self.assertEqual(
            result[0].optimized_bullets[1],
            "Wrote integration tests with pytest covering core endpoints",
        )

    def test_unmatched_project_name_is_skipped_but_matched_ones_still_returned(self):
        original_projects = [
            {"name": "Real Project", "technologies": [], "description": ["Did a real thing"]},
            {"name": "Other Real Project", "technologies": [], "description": ["Did another real thing"]},
        ]
        optimized = [
            Project(name="Real Project", technologies=[], description=["Did a real thing well"]),
            # No matching original for this one -- must not be trusted/surfaced at all.
            Project(name="Hallucinated Project", technologies=[], description=["Invented a thing"]),
        ]

        result = extract_optimized_projects(original_projects, optimized)

        names = [p.project_name for p in result]
        self.assertIn("Real Project", names)
        self.assertNotIn("Hallucinated Project", names)

    def test_falls_back_to_originals_when_nothing_matches(self):
        original_projects = [{"name": "Real Project", "technologies": [], "description": ["Did a thing"]}]
        optimized = [Project(name="Totally Different", technologies=[], description=["Invented a thing"])]

        result = extract_optimized_projects(original_projects, optimized)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].project_name, "Real Project")
        self.assertEqual(result[0].optimized_bullets, ["Did a thing"])


class ProjectsWithoutOriginalBulletsTests(unittest.TestCase):
    def test_synthesizes_a_bullet_from_technologies(self):
        original_projects = [
            {"name": "Portfolio Site", "technologies": ["Next.js", "Tailwind"], "description": []}
        ]
        optimized = [
            Project(
                name="Portfolio Site",
                technologies=["Next.js", "Tailwind"],
                description=["Architected a scalable multi-tenant platform"],  # ungrounded
            )
        ]

        result = extract_optimized_projects(original_projects, optimized)

        self.assertEqual(len(result), 1)
        self.assertEqual(
            result[0].optimized_bullets, ["Built Portfolio Site using Next.js, Tailwind."]
        )

    def test_synthesized_bullet_caps_technologies_at_four(self):
        original_projects = [
            {
                "name": "Kitchen Sink",
                "technologies": ["A", "B", "C", "D", "E", "F"],
                "description": [],
            }
        ]
        optimized = [Project(name="Kitchen Sink", technologies=[], description=[])]

        result = extract_optimized_projects(original_projects, optimized)

        self.assertEqual(result[0].optimized_bullets, ["Built Kitchen Sink using A, B, C, D."])

    def test_project_with_no_content_at_all_is_dropped_with_a_warning(self):
        original_projects = [
            {"name": "Empty Project", "technologies": [], "description": []},
            {"name": "Real Project", "technologies": [], "description": ["Did a real thing"]},
        ]
        optimized = [
            Project(name="Empty Project", technologies=[], description=["Invented something"]),
            Project(name="Real Project", technologies=[], description=["Did a real thing well"]),
        ]

        with self.assertLogs("backend.services.ats_scoring", level="WARNING") as logs:
            result = extract_optimized_projects(original_projects, optimized)

        self.assertEqual([p.project_name for p in result], ["Real Project"])
        self.assertIn("no groundable content", logs.output[0])


class VerifyExperienceGroundingTests(unittest.TestCase):
    def setUp(self):
        self.original_experience = [
            {
                "company": "Acme Corp",
                "title": "Backend Engineer",
                "responsibilities": [
                    "Built a REST API using Flask and PostgreSQL for inventory tracking",
                    "Wrote integration tests with pytest covering core endpoints",
                ],
            }
        ]

    def test_grounded_rewrite_is_kept_and_fabrication_falls_back(self):
        optimized = [
            Experience(
                company="Acme Corp",
                title="Backend Engineer",
                responsibilities=[
                    "Engineered a Flask/PostgreSQL REST API to track inventory in real time",
                    "Led a team of 12 engineers to migrate infrastructure to Kubernetes",
                ],
            )
        ]

        result = verify_experience_grounding(self.original_experience, optimized)

        self.assertEqual(len(result), 1)
        self.assertEqual(
            result[0].responsibilities[0],
            "Engineered a Flask/PostgreSQL REST API to track inventory in real time",
        )
        self.assertEqual(
            result[0].responsibilities[1],
            "Wrote integration tests with pytest covering core endpoints",
        )

    def test_reworded_title_still_matches_on_company(self):
        optimized = [
            Experience(
                company="Acme Corp",
                title="Backend Software Engineer",
                responsibilities=["Fabricated claim about leading a Kubernetes migration"],
            )
        ]

        result = verify_experience_grounding(self.original_experience, optimized)

        self.assertEqual(len(result), 1)
        # Matched on company alone, so the fabricated line fell back to the
        # original responsibility at that position instead of surviving.
        self.assertEqual(
            result[0].responsibilities,
            [self.original_experience[0]["responsibilities"][0]],
        )

    def test_unmatched_company_is_dropped(self):
        optimized = [
            Experience(company="Acme Corp", title="Backend Engineer", responsibilities=[]),
            Experience(company="Never Worked Here", title="CTO", responsibilities=["Ran the company"]),
        ]

        with self.assertLogs("backend.services.ats_scoring", level="WARNING"):
            result = verify_experience_grounding(self.original_experience, optimized)

        self.assertEqual([e.company for e in result], ["Acme Corp"])


class OptimizationSkillDeltaTests(unittest.TestCase):
    def _ats_score(self) -> ATSScore:
        return ATSScore(
            overall_score=50,
            skill_match_pct=50,
            required_skills_covered=["Python"],
            required_skills_missing=["Docker"],
            preferred_skills_covered=[],
            preferred_skills_missing=[],
            project_relevance_score=50,
            experience_relevance_score=50,
            education_match_score=50,
        )

    def test_logs_the_delta_between_pre_and_post_optimization_coverage(self):
        optimized_resume = {
            "skills": [{"category": "Tools", "skills": ["Python", "Docker"]}],
        }

        with self.assertLogs("backend.services.ats_scoring", level="INFO") as logs:
            after = log_optimization_skill_delta(
                optimized_resume, self._ats_score(), "user-1", "job-1"
            )

        self.assertEqual(after, 100)
        self.assertIn("skill_match_pct from 50 to 100", logs.output[0])

    def test_returns_none_without_an_ats_score(self):
        self.assertIsNone(log_optimization_skill_delta({}, None, "user-1", "job-1"))


class FlattenResumeSkillTermsTests(unittest.TestCase):
    def test_reads_an_unwrapped_resume_dict(self):
        terms = flatten_resume_skill_terms(
            {
                "skills": [{"category": "Languages", "skills": ["Python"]}],
                "projects": [{"technologies": ["Docker"]}],
            }
        )
        self.assertEqual(terms, {"python", "docker"})


class FlattenProfileSkillTermsTests(unittest.TestCase):
    def test_collects_skills_technologies_certifications_and_languages(self):
        profile_data = {
            "original_resume": {
                "skills": [{"category": "Languages", "skills": ["Python", "SQL"]}],
                "projects": [{"technologies": ["Docker"]}],
                "certifications": [{"name": "AWS Certified Developer"}],
                "languages": ["Spanish"],
            }
        }

        terms = flatten_profile_skill_terms(profile_data)

        self.assertEqual(
            terms,
            {"python", "sql", "docker", "aws certified developer", "spanish"},
        )


if __name__ == "__main__":
    unittest.main()
