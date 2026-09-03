import unittest

from backend.services import taxonomy


class ClassifyTitleTests(unittest.TestCase):
    def test_classifies_representative_titles_per_family(self):
        cases = {
            "Senior Frontend Developer": "frontend",
            "Front-End Engineer": "frontend",
            "React Developer": "frontend",
            "Backend Engineer": "backend",
            "Back-End Developer": "backend",
            "Python Developer": "backend",
            "Full Stack Engineer": "fullstack",
            "Fullstack Developer": "fullstack",
            "Mobile Engineer": "mobile",
            "iOS Developer": "mobile",
            "Android Engineer": "mobile",
            "Data Engineer": "data-engineering",
            "ETL Developer": "data-engineering",
            "Data Scientist": "data-science",
            "Machine Learning Engineer": "ml-engineering",
            "NLP Engineer": "ml-engineering",
            "DevOps Engineer": "devops-sre",
            "Site Reliability Engineer": "devops-sre",
            "Platform Engineer": "devops-sre",
            "Cloud Engineer": "cloud-infra",
            "QA Engineer": "qa-testing",
            "SDET": "qa-testing",
            "Security Engineer": "security",
            "Embedded Systems Engineer": "embedded",
            "Product Designer": "product-design",
            "Technical Writer": "technical-writing",
        }
        for title, expected_family in cases.items():
            with self.subTest(title=title):
                self.assertEqual(taxonomy.classify_title(title), expected_family)

    def test_ambiguous_titles_return_none_rather_than_guess(self):
        for title in ["Consultant", "Analyst", "Software Engineer", "Manager", ""]:
            with self.subTest(title=title):
                self.assertIsNone(taxonomy.classify_title(title))

    def test_classify_title_is_case_insensitive(self):
        self.assertEqual(taxonomy.classify_title("devops engineer"), "devops-sre")
        self.assertEqual(taxonomy.classify_title("DEVOPS ENGINEER"), "devops-sre")


class CanonicalizeSkillsTests(unittest.TestCase):
    def test_collapses_known_aliases_to_canonical_form(self):
        result = taxonomy.canonicalize_skills(["ReactJS", "React.js", "react", "javascript"])
        self.assertEqual(result, ["React", "JavaScript"])

    def test_deduplicates_preserving_first_seen_order(self):
        result = taxonomy.canonicalize_skills(["Python", "python3", "Go", "python"])
        self.assertEqual(result, ["Python", "Go"])

    def test_unknown_skill_passes_through_title_cased(self):
        result = taxonomy.canonicalize_skills(["some obscure tool"])
        self.assertEqual(result, ["Some Obscure Tool"])

    def test_blank_entries_are_dropped(self):
        result = taxonomy.canonicalize_skills(["Python", "  ", ""])
        self.assertEqual(result, ["Python"])


class AdjacentFamiliesTests(unittest.TestCase):
    _APPLICATION_DEV_FAMILIES = {"frontend", "backend", "fullstack", "mobile"}

    def test_devops_sre_has_no_application_dev_family_as_neighbor(self):
        neighbors = set(taxonomy.ADJACENT_FAMILIES.get("devops-sre", []))
        self.assertFalse(neighbors & self._APPLICATION_DEV_FAMILIES)

    def test_no_application_dev_family_lists_devops_sre_as_a_neighbor(self):
        for family in self._APPLICATION_DEV_FAMILIES:
            with self.subTest(family=family):
                self.assertNotIn("devops-sre", taxonomy.ADJACENT_FAMILIES.get(family, []))

    def test_every_family_has_an_adjacency_entry(self):
        for family in taxonomy.ROLE_FAMILIES:
            with self.subTest(family=family):
                self.assertIn(family, taxonomy.ADJACENT_FAMILIES)


if __name__ == "__main__":
    unittest.main()
