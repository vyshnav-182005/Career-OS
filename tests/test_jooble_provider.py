import unittest
from unittest.mock import Mock, patch

from backend.services.job_providers.jooble_provider import JoobleProvider


def _response(jobs):
    response = Mock()
    response.raise_for_status = Mock()
    response.json = Mock(return_value={"jobs": jobs})
    return response


class JoobleSkillExtractionTests(unittest.TestCase):
    """
    Jooble supplies no skills field, and this provider used to store an empty
    list for every job it returned. That zeroed the skill_overlap feature for
    the bulk of the non-software inventory, since Jooble is where the hardware,
    mechanical and civil postings come from. Skills are now mined from the
    snippet, the same way the ATS providers mine their descriptions.
    """

    def _fetch(self, snippet: str, title: str = "RF Engineer"):
        payload = [{
            "id": "1",
            "title": title,
            "company": "Acme",
            "location": "Remote",
            "snippet": snippet,
            "link": "https://example.com/1",
        }]
        with patch(
            "backend.services.job_providers.jooble_provider.requests.post",
            return_value=_response(payload),
        ):
            return JoobleProvider().fetch_jobs("RF Engineer")

    def test_mines_hardware_skills_from_the_snippet(self):
        jobs = self._fetch(
            "Design RF front ends, write Verilog for the FPGA, and lay out boards in Altium."
        )
        self.assertEqual(len(jobs), 1)
        for expected in ["Verilog", "FPGA", "Altium Designer"]:
            with self.subTest(skill=expected):
                self.assertIn(expected, jobs[0].skills)

    def test_mines_security_skills_from_the_snippet(self):
        jobs = self._fetch(
            "Run penetration tests with Burp Suite and Metasploit; report against OWASP.",
            title="Penetration Tester",
        )
        for expected in ["Burp Suite", "Metasploit", "OWASP"]:
            with self.subTest(skill=expected):
                self.assertIn(expected, jobs[0].skills)

    def test_snippet_without_known_skills_yields_empty_list(self):
        """Extraction never guesses, so an uninformative snippet stays empty."""
        jobs = self._fetch("An exciting opportunity with a fast growing team.")
        self.assertEqual(jobs[0].skills, [])


if __name__ == "__main__":
    unittest.main()
