import unittest
from unittest.mock import patch

from backend.models.schemas import OptimizationRequest, OptimizationResponse
from backend.services import workflow_orchestrator
from backend.agents.resume_optimization_agent import ResumeOptimizationTimeoutError


class ResumeOptimizationWorkflowTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        workflow_orchestrator.workflow_runs.clear()
        self.request = OptimizationRequest(
            user_id="user-123",
            job_title="Backend Engineer",
            job_description="Build reliable APIs.",
        )

    async def test_submit_resume_optimization_workflow_creates_queued_run(self):
        response = await workflow_orchestrator.submit_resume_optimization_workflow(self.request)

        self.assertTrue(response.success)
        self.assertEqual("Resume optimization workflow queued.", response.message)
        self.assertEqual("queued", response.data["status"])
        self.assertIn(response.data["workflow_id"], workflow_orchestrator.workflow_runs)

    async def test_run_resume_optimization_workflow_records_successful_result(self):
        response = await workflow_orchestrator.submit_resume_optimization_workflow(self.request)
        workflow_id = response.data["workflow_id"]
        optimization_response = OptimizationResponse(
            success=True,
            message="Resume optimized successfully.",
            html_content="<html>ok</html>",
            pdf_content="base64-pdf",
        )

        with patch.object(
            workflow_orchestrator,
            "optimize_resume_service",
            return_value=optimization_response,
        ):
            await workflow_orchestrator.run_resume_optimization_workflow(workflow_id, self.request)

        status = workflow_orchestrator.get_resume_optimization_workflow_status(workflow_id)
        self.assertEqual("succeeded", status.status)
        self.assertEqual("Resume optimized successfully.", status.message)
        self.assertEqual("base64-pdf", status.data["pdf_content"])

    async def test_run_resume_optimization_workflow_marks_provider_timeout(self):
        response = await workflow_orchestrator.submit_resume_optimization_workflow(self.request)
        workflow_id = response.data["workflow_id"]

        with patch.object(
            workflow_orchestrator,
            "optimize_resume_service",
            side_effect=ResumeOptimizationTimeoutError("Request timed out."),
        ):
            await workflow_orchestrator.run_resume_optimization_workflow(workflow_id, self.request)

        status = workflow_orchestrator.get_resume_optimization_workflow_status(workflow_id)
        self.assertEqual("timed_out", status.status)
        self.assertIn("timed out", status.message.lower())


if __name__ == "__main__":
    unittest.main()
