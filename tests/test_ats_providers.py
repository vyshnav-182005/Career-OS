import unittest
from unittest.mock import patch

from backend.services import job_ingestion, taxonomy
from backend.services.job_ingestion import JobIngestionWorkflow
from backend.services.job_providers import ats_base
from backend.services.job_providers.ats_base import ATSBoardProvider, BoardCompany, infer_employment_type, matches_query
from backend.services.job_providers.greenhouse_provider import GreenhouseProvider
from backend.services.job_providers.lever_provider import LeverProvider


GREENHOUSE_PAYLOAD = {
    "jobs": [
        {
            "id": 4012345,
            "title": "Senior Backend Engineer",
            "absolute_url": "https://boards.greenhouse.io/acme/jobs/4012345",
            "first_published": "2026-08-11T14:22:07-04:00",
            "location": {"name": "Bengaluru, India"},
            # Double-encoded HTML, exactly as Greenhouse returns it.
            "content": "&lt;p&gt;We use &lt;strong&gt;Python&lt;/strong&gt;, PostgreSQL and Kubernetes.&lt;/p&gt;",
        },
        {
            "id": 4012346,
            "title": "Software Engineering Intern",
            "absolute_url": "https://boards.greenhouse.io/acme/jobs/4012346",
            "updated_at": "2026-08-01T00:00:00Z",
            "offices": [{"name": "Remote"}],
            "content": "&lt;p&gt;Learn React and TypeScript.&lt;/p&gt;",
        },
        {"id": None, "title": "Broken"},  # dropped
    ]
}

LEVER_PAYLOAD = [
    {
        "id": "7f3b0c1e-1111-2222-3333-444455556666",
        "text": "Frontend Engineer",
        "createdAt": 1786000000000,
        "categories": {"location": "Remote (India)", "commitment": "Full-time"},
        "description": "<p>Build the dashboard.</p>",
        "lists": [{"text": "Requirements", "content": "<ul><li>3+ years of React and TypeScript</li></ul>"}],
        "additional": "<p>We offer equity.</p>",
        "hostedUrl": "https://jobs.lever.co/acme/7f3b0c1e",
    },
    {
        "id": "8a4c1d2f-aaaa-bbbb-cccc-ddddeeeeffff",
        "text": "Data Science Contractor",
        "createdAt": 1786000000000,
        "categories": {"allLocations": ["Mumbai"], "commitment": "Contract"},
        "description": "<p>Work with Python and SQL.</p>",
        "hostedUrl": "https://jobs.lever.co/acme/8a4c1d2f",
    },
]


class GreenhouseParsingTests(unittest.TestCase):
    def setUp(self):
        self.company = BoardCompany(token="acme", name="Acme")
        self.provider = GreenhouseProvider(companies=[self.company], use_cache=False)

    def test_parses_jobs_and_namespaces_ids_by_board(self):
        jobs = self.provider.parse_board(self.company, GREENHOUSE_PAYLOAD)

        self.assertEqual(len(jobs), 2)
        self.assertEqual(jobs[0].provider, "greenhouse")
        self.assertEqual(jobs[0].provider_job_id, "acme:4012345")
        self.assertEqual(jobs[0].company, "Acme")
        self.assertEqual(jobs[0].location, "Bengaluru, India")
        self.assertEqual(jobs[0].url, "https://boards.greenhouse.io/acme/jobs/4012345")

    def test_double_encoded_html_is_decoded_to_plain_prose(self):
        job = self.provider.parse_board(self.company, GREENHOUSE_PAYLOAD)[0]

        self.assertNotIn("<", job.description)
        self.assertNotIn("&lt;", job.description)
        self.assertIn("Python", job.description)

    def test_skills_extracted_from_full_description(self):
        job = self.provider.parse_board(self.company, GREENHOUSE_PAYLOAD)[0]

        self.assertIn("Python", job.skills)
        self.assertIn("Kubernetes", job.skills)

    def test_employment_type_inferred_from_title(self):
        jobs = self.provider.parse_board(self.company, GREENHOUSE_PAYLOAD)

        self.assertEqual(jobs[0].employment_type, "full_time")
        self.assertEqual(jobs[1].employment_type, "internship")

    def test_office_used_when_location_absent(self):
        jobs = self.provider.parse_board(self.company, GREENHOUSE_PAYLOAD)

        self.assertEqual(jobs[1].location, "Remote")


class LeverParsingTests(unittest.TestCase):
    def setUp(self):
        self.company = BoardCompany(token="acme", name="Acme")
        self.provider = LeverProvider(companies=[self.company], use_cache=False)

    def test_description_assembled_from_description_lists_and_additional(self):
        job = self.provider.parse_board(self.company, LEVER_PAYLOAD)[0]

        # All three Lever sections must survive, or the JD the LLM sees is partial.
        self.assertIn("Build the dashboard", job.description)
        self.assertIn("Requirements", job.description)
        self.assertIn("3+ years of React", job.description)
        self.assertIn("equity", job.description)

    def test_commitment_maps_to_employment_type(self):
        jobs = self.provider.parse_board(self.company, LEVER_PAYLOAD)

        self.assertEqual(jobs[0].employment_type, "full_time")
        self.assertEqual(jobs[1].employment_type, "contract")

    def test_all_locations_fallback_does_not_index_error_when_empty(self):
        payload = [dict(LEVER_PAYLOAD[1], categories={"allLocations": []})]

        job = self.provider.parse_board(self.company, payload)[0]

        self.assertIsNone(job.location)

    def test_epoch_millis_timestamp_parsed(self):
        job = self.provider.parse_board(self.company, LEVER_PAYLOAD)[0]

        self.assertEqual(job.posted_date.year, 2026)


class QueryFilteringTests(unittest.TestCase):
    def test_matches_on_role_family_not_just_exact_string(self):
        # Both classify as `backend`, so a backend search should surface it.
        self.assertTrue(matches_query("Senior Backend Engineer", "Backend Developer"))

    def test_rejects_a_different_family(self):
        self.assertFalse(matches_query("Frontend Engineer", "Backend Developer"))

    def test_falls_back_to_word_overlap_when_unclassifiable(self):
        self.assertTrue(matches_query("Technical Program Manager", "program manager"))
        self.assertFalse(matches_query("Technical Program Manager", "veterinary surgeon"))

    def test_empty_query_matches_everything(self):
        self.assertTrue(matches_query("Anything At All", ""))


class SkillExtractionTests(unittest.TestCase):
    def test_extracts_known_skills(self):
        skills = taxonomy.extract_skills("Strong Python and JavaScript experience, plus Docker.")

        self.assertIn("Python", skills)
        self.assertIn("JavaScript", skills)
        self.assertIn("Docker", skills)

    def test_short_ambiguous_aliases_do_not_fire_on_prose(self):
        # "go", "r" and "c" as bare words must not become skills.
        skills = taxonomy.extract_skills("You will go far here. We move fast, c'est la vie.")

        self.assertNotIn("Go", skills)
        self.assertNotIn("R", skills)
        self.assertNotIn("C", skills)

    def test_respects_limit_and_preserves_first_seen_order(self):
        skills = taxonomy.extract_skills("Python then Docker then Kubernetes", limit=2)

        self.assertEqual(skills, ["Python", "Docker"])


class _StubBoardProvider(ATSBoardProvider):
    """Exercises the fan-out without network: every board fails."""

    vendor = "stub"

    def board_url(self, company):
        return f"https://example.invalid/{company.token}"

    def parse_board(self, company, payload):
        return []


class PartialFetchExpirationTests(unittest.TestCase):
    def setUp(self):
        ats_base.clear_board_cache()

    def test_no_configured_boards_reports_incomplete(self):
        provider = _StubBoardProvider(companies=[], use_cache=False)

        provider.fetch_jobs()

        # Reporting "complete" on an empty config would expire the whole table.
        self.assertFalse(provider.fetch_complete)

    def test_ingestion_skips_expiration_when_fetch_incomplete(self):
        provider = _StubBoardProvider(companies=[], use_cache=False)
        workflow = JobIngestionWorkflow(providers=[provider])

        with patch.object(job_ingestion, "get_active_provider_job_hashes", return_value={"live-1": "hash"}), \
             patch.object(job_ingestion, "upsert_jobs"), \
             patch.object(job_ingestion, "delete_expired_jobs") as mock_delete:
            stats = workflow.run()

        mock_delete.assert_not_called()
        self.assertEqual(stats.expired, 0)


class DedupTests(unittest.TestCase):
    def test_duplicate_provider_job_ids_collapse(self):
        # Two rows with the same (provider, provider_job_id) in one upsert
        # payload is a hard Postgres error, so the fan-out must dedupe.
        company = BoardCompany(token="acme", name="Acme")
        provider = GreenhouseProvider(companies=[company, company], use_cache=False)

        with patch.object(provider, "_fetch_one", return_value=(True, provider.parse_board(company, GREENHOUSE_PAYLOAD))):
            jobs = provider.fetch_jobs()

        self.assertEqual(len(jobs), 2)
        self.assertEqual(len({job.provider_job_id for job in jobs}), 2)


class EmploymentTypeTests(unittest.TestCase):
    def test_inference(self):
        self.assertEqual(infer_employment_type("Backend Engineer Intern"), "internship")
        self.assertEqual(infer_employment_type("Part-Time Designer"), "part_time")
        self.assertEqual(infer_employment_type("Contract Data Analyst"), "contract")
        self.assertEqual(infer_employment_type("Staff Engineer"), "full_time")


if __name__ == "__main__":
    unittest.main()
