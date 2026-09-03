import unittest
from unittest.mock import AsyncMock, patch

from backend.models.resume import ParsedResume
from backend.models.schemas import OptimizationRequest
from backend.services import resume_optimizer


class ResumeOptimizerJobIdTests(unittest.IsolatedAsyncioTestCase):
    async def test_resolves_job_title_and_description_from_job_id(self):
        request = OptimizationRequest(user_id="user-123", job_id="job-abc")
        job_row = {
            "title": "Backend Engineer",
            "description": "Build reliable APIs.",
            "skills": ["Python", "FastAPI"],
        }

        with patch.object(resume_optimizer, "get_job_by_id", return_value=job_row) as mock_get_job, \
             patch.object(
                 resume_optimizer, "run_resume_optimization", new_callable=AsyncMock
             ) as mock_run, \
             patch.object(resume_optimizer, "render_resume_to_html", return_value="<html>ok</html>"), \
             patch.object(
                 resume_optimizer, "compile_html_to_pdf_base64", new_callable=AsyncMock
             ) as mock_pdf:
            mock_run.return_value = ParsedResume()
            mock_pdf.return_value = "base64-pdf"

            response = await resume_optimizer.optimize_resume_service(request)

        mock_get_job.assert_called_once_with("job-abc")
        mock_run.assert_awaited_once()
        _, kwargs = mock_run.call_args
        self.assertEqual(kwargs["job_title"], "Backend Engineer")
        self.assertIn("Build reliable APIs.", kwargs["job_description"])
        self.assertIn("Python, FastAPI", kwargs["job_description"])
        self.assertTrue(response.success)

    async def test_returns_failure_when_job_not_found(self):
        request = OptimizationRequest(user_id="user-123", job_id="missing-job")

        with patch.object(resume_optimizer, "get_job_by_id", return_value=None):
            response = await resume_optimizer.optimize_resume_service(request)

        self.assertFalse(response.success)
        self.assertEqual("Job not found.", response.message)

    async def test_returns_failure_when_no_job_reference_supplied(self):
        request = OptimizationRequest(user_id="user-123")

        response = await resume_optimizer.optimize_resume_service(request)

        self.assertFalse(response.success)
        self.assertIn("job_id", response.message)


if __name__ == "__main__":
    unittest.main()
