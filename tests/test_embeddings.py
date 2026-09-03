import unittest
from unittest.mock import MagicMock, patch

from backend.services import embeddings


PROFILE_DATA = {
    "original_resume": {
        "personal_info": {"summary": "Backend engineer who loves distributed systems."},
        "experience": [
            {"title": "Senior Backend Engineer"},
            {"title": "Backend Engineer"},
        ],
        "skills": [
            {"category": "Languages", "skills": ["Python", "Go"]},
            {"category": "Frameworks", "skills": ["FastAPI"]},
        ],
        "projects": [
            {"name": "Order Service", "technologies": ["Python", "PostgreSQL"]},
        ],
    },
    "preferred_job_roles": [{"title": "Backend Engineer", "confidence": "High", "reasoning": "x"}],
    "strengths": ["System design", "API design"],
}


class BuildProfileEmbeddingTextTests(unittest.TestCase):
    def test_uses_personal_info_summary_not_top_level_summary(self):
        text = embeddings.build_profile_embedding_text(PROFILE_DATA)
        self.assertIn("Backend engineer who loves distributed systems.", text)

    def test_flattens_skills_across_categories_and_projects(self):
        text = embeddings.build_profile_embedding_text(PROFILE_DATA)
        skills_line = text.split("\n")[1]
        self.assertTrue(skills_line.startswith("Skills:"))
        for skill in ["Python", "Go", "FastAPI", "PostgreSQL"]:
            self.assertIn(skill, skills_line)
        # Python appears in both a skill category and a project's technologies
        # and should not be duplicated.
        self.assertEqual(skills_line.count("Python"), 1)

    def test_mirrors_job_side_shape_with_title_and_skills_first(self):
        text = embeddings.build_profile_embedding_text(PROFILE_DATA)
        lines = text.split("\n")
        self.assertTrue(lines[0].startswith("Title:"))
        self.assertTrue(lines[1].startswith("Skills:"))
        self.assertTrue(lines[2].startswith("Description:"))
        self.assertIn("Backend Engineer", lines[0])
        self.assertIn("Senior Backend Engineer", lines[0])

    def test_missing_fields_fall_back_to_placeholders(self):
        text = embeddings.build_profile_embedding_text({})
        self.assertIn("Title: Not specified", text)
        self.assertIn("Skills: No specific skills", text)
        self.assertIn("Description: No summary available", text)

    def test_truncates_to_max_words_preserving_title_and_skills(self):
        huge_profile = {
            "original_resume": {
                "personal_info": {"summary": " ".join(f"word{i}" for i in range(500))},
                "skills": [{"category": "Languages", "skills": ["Python"]}],
            },
            "preferred_job_roles": [{"title": "Backend Engineer"}],
            "strengths": [],
        }
        text = embeddings.build_profile_embedding_text(huge_profile)
        word_count = len(text.split())
        self.assertLessEqual(word_count, embeddings.PROFILE_EMBEDDING_MAX_WORDS)
        self.assertIn("Title: Backend Engineer", text)
        self.assertIn("Skills: Python", text)


class GenerateProfileEmbeddingTests(unittest.TestCase):
    def test_encodes_built_text_and_returns_list(self):
        fake_model = MagicMock()
        fake_model.encode.return_value.tolist.return_value = [0.1, 0.2, 0.3]

        with patch.object(embeddings, "get_model", return_value=fake_model):
            result = embeddings.generate_profile_embedding(PROFILE_DATA)

        self.assertEqual(result, [0.1, 0.2, 0.3])
        encoded_text = fake_model.encode.call_args[0][0]
        self.assertTrue(encoded_text.startswith("Title:"))

    def test_returns_empty_list_on_failure(self):
        with patch.object(embeddings, "get_model", side_effect=RuntimeError("boom")):
            result = embeddings.generate_profile_embedding(PROFILE_DATA)

        self.assertEqual(result, [])


if __name__ == "__main__":
    unittest.main()
