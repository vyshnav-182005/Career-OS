from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from backend.models.schemas import OptimizationRequest
from backend.models.schemas import WorkflowResponse, WorkflowStatusResponse
from backend.services.workflow_orchestrator import (
    get_resume_optimization_workflow_status,
    run_resume_optimization_workflow,
    submit_resume_optimization_workflow,
)

router = APIRouter(
    prefix="/workflows",
    tags=["Workflow Orchestrator"],
)

@router.post("/resume-optimize", response_model=WorkflowResponse, status_code=status.HTTP_202_ACCEPTED)
async def optimize_resume_workflow(request: OptimizationRequest, background_tasks: BackgroundTasks):
    """
    Queue the Resume Optimization Workflow via the Orchestrator.
    """
    response = await submit_resume_optimization_workflow(request)
    background_tasks.add_task(
        run_resume_optimization_workflow,
        response.data["workflow_id"],
        request,
    )
    return response

@router.get("/{workflow_id}", response_model=WorkflowStatusResponse)
async def get_workflow_status(workflow_id: str):
    """
    Get the current status of a queued workflow.
    """
    response = get_resume_optimization_workflow_status(workflow_id)
    if response is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow not found.",
        )
    return response
