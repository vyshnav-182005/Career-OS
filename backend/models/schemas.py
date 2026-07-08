from pydantic import BaseModel
from typing import Optional

class WorkflowResponse(BaseModel):
    success: bool
    message: str
    data: Optional[dict] = None

class WorkflowStatusResponse(BaseModel):
    workflow_id: str
    status: str
    message: str
    data: Optional[dict] = None

class OptimizationRequest(BaseModel):
    user_id: str
    job_description: str
    job_title: str

class OptimizationResponse(BaseModel):
    success: bool
    message: str
    optimized_resume_json: Optional[dict] = None
    html_content: Optional[str] = None
    pdf_content: Optional[str] = None
