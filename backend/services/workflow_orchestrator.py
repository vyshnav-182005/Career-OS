import logging
from uuid import uuid4
from backend.agents.resume_parsing_agent import run_profile_intelligence
from backend.agents.resume_optimization_agent import ResumeOptimizationTimeoutError
from backend.services.resume_optimizer import optimize_resume_service
from backend.models.schemas import OptimizationRequest, OptimizationResponse
from backend.models.schemas import WorkflowResponse, WorkflowStatusResponse

logger = logging.getLogger(__name__)

workflow_runs: dict[str, WorkflowStatusResponse] = {}

async def trigger_profile_intelligence_workflow(user_id: str):
    """
    Orchestrates the Profile Intelligence workflow.
    This can handle retries, status updates in DB, and error logging centrally.
    """
    logger.info("Orchestrator: Starting Profile Intelligence Workflow for user=%s", user_id)
    try:
        # If we had a workflow_runs table, we'd log START here
        await run_profile_intelligence(user_id)
        # We'd log SUCCESS here
        logger.info("Orchestrator: Completed Profile Intelligence Workflow for user=%s", user_id)
    except Exception as e:
        logger.error("Orchestrator: Failed Profile Intelligence Workflow for user=%s: %s", user_id, e)
        # We'd log FAILURE here

async def submit_resume_optimization_workflow(request: OptimizationRequest) -> WorkflowResponse:
    workflow_id = str(uuid4())
    workflow_runs[workflow_id] = WorkflowStatusResponse(
        workflow_id=workflow_id,
        status="queued",
        message="Resume optimization workflow queued.",
    )
    logger.info("Orchestrator: Queued Resume Optimization Workflow id=%s user=%s", workflow_id, request.user_id)
    return WorkflowResponse(
        success=True,
        message="Resume optimization workflow queued.",
        data={"workflow_id": workflow_id, "status": "queued"},
    )

def get_resume_optimization_workflow_status(workflow_id: str) -> WorkflowStatusResponse | None:
    return workflow_runs.get(workflow_id)

async def run_resume_optimization_workflow(workflow_id: str, request: OptimizationRequest) -> None:
    """
    Executes a queued Resume Optimization workflow and records its terminal state.
    """
    if workflow_id not in workflow_runs:
        logger.error("Orchestrator: Unknown Resume Optimization Workflow id=%s", workflow_id)
        return

    workflow_runs[workflow_id] = WorkflowStatusResponse(
        workflow_id=workflow_id,
        status="running",
        message="Resume optimization workflow running.",
    )
    logger.info("Orchestrator: Starting Resume Optimization Workflow id=%s user=%s", workflow_id, request.user_id)
    try:
        result: OptimizationResponse = await optimize_resume_service(request)

        if result.success:
            workflow_runs[workflow_id] = WorkflowStatusResponse(
                workflow_id=workflow_id,
                status="succeeded",
                message=result.message,
                data={"html_content": result.html_content, "pdf_content": result.pdf_content},
            )
            logger.info("Orchestrator: Completed Resume Optimization Workflow id=%s user=%s", workflow_id, request.user_id)
        else:
            workflow_runs[workflow_id] = WorkflowStatusResponse(
                workflow_id=workflow_id,
                status="failed",
                message=result.message,
            )
            logger.error("Orchestrator: Resume Optimization Workflow failed id=%s user=%s: %s", workflow_id, request.user_id, result.message)
    except ResumeOptimizationTimeoutError as e:
        workflow_runs[workflow_id] = WorkflowStatusResponse(
            workflow_id=workflow_id,
            status="timed_out",
            message="Resume optimization timed out while waiting for the AI provider. Please retry in a few minutes.",
        )
        logger.error("Orchestrator: Resume Optimization Workflow timed out id=%s user=%s: %s", workflow_id, request.user_id, e)
    except Exception as e:
        workflow_runs[workflow_id] = WorkflowStatusResponse(
            workflow_id=workflow_id,
            status="failed",
            message="An unexpected error occurred during the workflow.",
        )
        logger.error("Orchestrator: Unexpected error in Resume Optimization Workflow id=%s user=%s: %s", workflow_id, request.user_id, e)

async def trigger_resume_optimization_workflow(request: OptimizationRequest) -> WorkflowResponse:
    """
    Backwards-compatible synchronous execution helper.
    """
    queued = await submit_resume_optimization_workflow(request)
    workflow_id = queued.data["workflow_id"]
    await run_resume_optimization_workflow(workflow_id, request)
    status = get_resume_optimization_workflow_status(workflow_id)
    return WorkflowResponse(
        success=status.status == "succeeded",
        message=status.message,
        data=status.data,
    )
