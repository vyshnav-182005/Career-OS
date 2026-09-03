import unittest

from backend.services.job_context import resolve_job_text
from backend.services.text_cleaning import clean_html_text, summarize_text


class CleanHtmlTextTests(unittest.TestCase):
    def test_strips_tags_and_keeps_block_structure(self):
        raw = "<p>We are hiring.</p><ul><li>Build APIs</li><li>Own CI/CD</li></ul>"

        self.assertEqual(
            clean_html_text(raw),
            "We are hiring.\n• Build APIs\n• Own CI/CD",
        )

    def test_decodes_named_and_numeric_entities(self):
        raw = "R&amp;D team&nbsp;&mdash; ship fast &#38; iterate &#x27;now&#x27;"

        cleaned = clean_html_text(raw)

        self.assertIn("R&D team", cleaned)
        self.assertIn("&", cleaned)
        self.assertNotIn("&amp;", cleaned)
        self.assertNotIn("&nbsp;", cleaned)
        self.assertNotIn("&#x27;", cleaned)

    def test_decodes_double_encoded_markup(self):
        """Providers routinely double-encode; one unescape pass leaves literal tags."""
        raw = "&lt;p&gt;Nice to have: Python&lt;/p&gt;&amp;nbsp;Go"

        cleaned = clean_html_text(raw)

        self.assertNotIn("<p>", cleaned)
        self.assertNotIn("&nbsp;", cleaned)
        self.assertIn("Nice to have: Python", cleaned)

    def test_drops_script_and_style_content(self):
        raw = "<style>.a{color:red}</style>Real text<script>alert('x')</script>"

        cleaned = clean_html_text(raw)

        self.assertEqual(cleaned, "Real text")

    def test_normalizes_bullet_glyphs_and_invisible_characters(self):
        raw = "- One\n* Two\n• Three​­"

        self.assertEqual(clean_html_text(raw), "• One\n• Two\n• Three")

    def test_collapses_whitespace_without_flattening_paragraphs(self):
        raw = "<p>First   para</p>\n\n\n\n<p>Second para</p>"

        self.assertEqual(clean_html_text(raw), "First para\n\nSecond para")

    def test_drops_provider_boilerplate_lines(self):
        self.assertEqual(clean_html_text("<p>Real content</p><p>Read more</p>"), "Real content")

    def test_empty_inputs_return_empty_string(self):
        self.assertEqual(clean_html_text(None), "")
        self.assertEqual(clean_html_text(""), "")
        self.assertEqual(clean_html_text("<div></div>"), "")


class SummarizeTextTests(unittest.TestCase):
    def test_truncates_on_a_word_boundary(self):
        summary = summarize_text("<p>" + "word " * 60 + "</p>", max_chars=40)

        self.assertLessEqual(len(summary), 41)  # 40 + the ellipsis
        self.assertTrue(summary.endswith("…"))
        self.assertFalse(summary.rstrip("…").endswith(" "))

    def test_short_text_is_returned_whole_without_ellipsis(self):
        self.assertEqual(summarize_text("<b>Short</b>", max_chars=40), "Short")


class ResolveJobTextTests(unittest.TestCase):
    def test_description_is_cleaned_before_reaching_the_llm(self):
        job = {"title": "Backend Engineer", "description": "<p>Build&nbsp;APIs</p>", "skills": []}

        title, description = resolve_job_text(job)

        self.assertEqual(title, "Backend Engineer")
        self.assertEqual(description, "Build APIs")

    def test_skills_are_appended_to_the_cleaned_description(self):
        job = {"title": "ML Engineer", "description": "<p>Train models</p>", "skills": ["Python", "PyTorch"]}

        _, description = resolve_job_text(job)

        self.assertIn("Train models", description)
        self.assertIn("Required/preferred skills: Python, PyTorch", description)

    def test_missing_fields_do_not_raise(self):
        title, description = resolve_job_text({})

        self.assertEqual(title, "")
        self.assertEqual(description, "")


if __name__ == "__main__":
    unittest.main()
