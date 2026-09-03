import re
import unittest

from backend.models.resume import ParsedResume, Experience, Project, normalize_bullets
from backend.services.resume_renderer import (
    DENSITY_COMPACT,
    DENSITY_RELAXED,
    _count_content_lines,
    compute_density,
    render_resume_to_html,
)


class NormalizeBulletsTests(unittest.TestCase):
    """
    Regression cover for the bug where generated resumes printed a literal
    "['...', '...']" array instead of bullet points.
    """

    def test_stringified_python_list_becomes_separate_bullets(self):
        value = "['Built a REST API', 'Cut latency by 40%']"

        self.assertEqual(normalize_bullets(value), ["Built a REST API", "Cut latency by 40%"])

    def test_stringified_json_array_becomes_separate_bullets(self):
        value = '["Trained a CNN", "Deployed to AWS"]'

        self.assertEqual(normalize_bullets(value), ["Trained a CNN", "Deployed to AWS"])

    def test_list_wrapping_a_stringified_list_is_unwrapped(self):
        self.assertEqual(normalize_bullets(["['A', 'B']"]), ["A", "B"])

    def test_newline_blob_splits_into_bullets(self):
        self.assertEqual(normalize_bullets("Did X\nDid Y"), ["Did X", "Did Y"])

    def test_leading_markers_are_stripped(self):
        self.assertEqual(normalize_bullets(["- Did X", "* Did Y", "• Did Z", "1. Did W"]),
                         ["Did X", "Did Y", "Did Z", "Did W"])

    def test_blanks_and_duplicates_are_dropped(self):
        self.assertEqual(normalize_bullets(["  A  ", "", None, "a"]), ["A"])

    def test_nested_structures_are_flattened(self):
        self.assertEqual(normalize_bullets([["A", "B"], {"k": "C"}]), ["A", "B", "C"])

    def test_none_and_empty_return_empty_list(self):
        self.assertEqual(normalize_bullets(None), [])
        self.assertEqual(normalize_bullets([]), [])

    def test_plain_lists_pass_through_unchanged(self):
        bullets = ["Shipped the ingestion pipeline.", "Owned the on-call rotation."]

        self.assertEqual(normalize_bullets(bullets), bullets)


class ModelValidatorTests(unittest.TestCase):
    def test_project_description_is_normalized_on_construction(self):
        project = Project(name="CareerOS", description="['Built retrieval', 'Added scoring']")

        self.assertEqual(project.description, ["Built retrieval", "Added scoring"])

    def test_experience_responsibilities_are_normalized_on_construction(self):
        experience = Experience(title="Engineer", responsibilities="['Shipped feature']")

        self.assertEqual(experience.responsibilities, ["Shipped feature"])

    def test_comma_joined_term_lists_are_split(self):
        project = Project(name="X", technologies="Python, FastAPI, Docker")
        resume = ParsedResume(languages="English, Malayalam")

        self.assertEqual(project.technologies, ["Python", "FastAPI", "Docker"])
        self.assertEqual(resume.languages, ["English", "Malayalam"])


def _resume(project_count=2, bullets=3):
    return ParsedResume(
        personal_info={
            "name": "Test Candidate",
            "email": "test@example.com",
            "summary": "Backend engineer building Python services and data pipelines.",
        },
        experience=[
            {
                "title": "Software Engineer",
                "company": "Acme",
                "start_date": "2024",
                "is_current": True,
                "responsibilities": [f"Shipped subsystem {i} serving 40k requests a day." for i in range(bullets)],
            }
        ],
        projects=[
            {
                "name": f"Project {i}",
                "technologies": ["Python", "FastAPI"],
                "description": [f"Implemented component {j} reducing latency." for j in range(bullets)],
            }
            for i in range(project_count)
        ],
        education=[{"institution": "CUSAT", "degree": "B.Tech", "field_of_study": "CS", "end_date": "2025"}],
        skills=[{"category": "Languages", "skills": ["Python", "SQL"]}],
        certifications=[{"name": "AWS Cloud Practitioner", "issuer": "Amazon", "date": "2024"}],
        languages=["English"],
    )


class TemplateRenderingTests(unittest.TestCase):
    def test_project_bullets_render_as_list_items_not_an_array(self):
        resume = ParsedResume(
            personal_info={"name": "Test"},
            projects=[{"name": "CareerOS", "description": "['Built retrieval', 'Added ATS scoring']"}],
        )

        html = render_resume_to_html(resume)

        self.assertIsNotNone(html)
        self.assertIn("<li>Built retrieval</li>", re.sub(r">\s+<", "><", html))
        # The literal array syntax must not survive into the document.
        self.assertNotIn("['Built retrieval'", html)
        self.assertNotIn("&#39;", html)

    def test_sections_previously_dropped_are_rendered(self):
        resume = _resume()

        html = render_resume_to_html(resume)

        self.assertIn("Certifications", html)
        self.assertIn("AWS Cloud Practitioner", html)
        self.assertIn("Languages", html)
        # Project technologies were parsed but never shown before.
        self.assertIn("Python, FastAPI", html)

    def test_custom_sections_and_publications_render(self):
        resume = ParsedResume(
            personal_info={"name": "Test"},
            publications=[{"title": "A Paper", "publisher": "IEEE", "date": "2025"}],
            custom_sections=[{"section_title": "Awards", "items": [{"title": "Best Project", "date": "2024"}]}],
        )

        html = render_resume_to_html(resume)

        self.assertIn("Publications", html)
        self.assertIn("A Paper", html)
        self.assertIn("Awards", html)
        self.assertIn("Best Project", html)

    def test_density_values_reach_the_stylesheet(self):
        resume = _resume()
        density = compute_density(resume)

        html = render_resume_to_html(resume)

        self.assertIn(f"--font-size: {density.font_size}pt", html)
        self.assertIn(f"--page-margin-v: {density.margin_v}mm", html)

    def test_empty_resume_still_renders(self):
        html = render_resume_to_html(ParsedResume())

        self.assertIsNotNone(html)
        self.assertIn("<body>", html)


class DensityTests(unittest.TestCase):
    def test_sparse_content_gets_the_most_generous_scale(self):
        sparse = ParsedResume(personal_info={"name": "Test"}, projects=[{"name": "One", "description": ["A bullet."]}])

        self.assertEqual(compute_density(sparse), DENSITY_RELAXED)

    def test_heavy_content_gets_the_tightest_scale(self):
        heavy = _resume(project_count=8, bullets=4)

        self.assertEqual(compute_density(heavy), DENSITY_COMPACT)

    def test_density_scales_monotonically_with_content(self):
        """More content must never produce larger type."""
        sizes = [compute_density(_resume(project_count=n, bullets=3)).font_size for n in range(1, 9)]

        self.assertEqual(sizes, sorted(sizes, reverse=True))

    def test_font_size_stays_within_the_calibrated_bounds(self):
        for n in range(1, 12):
            size = compute_density(_resume(project_count=n, bullets=4)).font_size
            self.assertGreaterEqual(size, DENSITY_COMPACT.font_size)
            self.assertLessEqual(size, DENSITY_RELAXED.font_size)

    def test_line_count_grows_with_content(self):
        self.assertLess(_count_content_lines(_resume(1, 2)), _count_content_lines(_resume(4, 4)))


if __name__ == "__main__":
    unittest.main()
