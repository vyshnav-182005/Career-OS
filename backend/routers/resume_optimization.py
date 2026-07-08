from fastapi import APIRouter, HTTPException, status
from backend.models.schemas import OptimizationRequest, OptimizationResponse
from backend.services.resume_optimizer import optimize_resume_service

router = APIRouter(
    prefix="/resume/optimize",
    tags=["Resume Optimization"],
)

@router.post("/", response_model=OptimizationResponse)
async def optimize_resume(request: OptimizationRequest):
    """
    Optimize a user's resume for a specific Job Description.
    """
    response = await optimize_resume_service(request)
    if not response.success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=response.message
        )
    return response
