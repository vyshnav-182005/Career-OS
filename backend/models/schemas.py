from pydantic import BaseModel, Field
from typing import Literal, Optional

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
    job_id: Optional[str] = None
    job_description: Optional[str] = None
    job_title: Optional[str] = None

class OptimizationResponse(BaseModel):
    success: bool
    message: str
    optimized_resume_json: Optional[dict] = None
    html_content: Optional[str] = None
    pdf_content: Optional[str] = None


class OptimizedProject(BaseModel):
    project_name: str
    technologies: list[str] = Field(default_factory=list)
    original_bullets: list[str] = Field(default_factory=list)
    optimized_bullets: list[str] = Field(default_factory=list)


class ATSScore(BaseModel):
    overall_score: int
    skill_match_pct: int
    required_skills_covered: list[str] = Field(default_factory=list)
    required_skills_missing: list[str] = Field(default_factory=list)
    preferred_skills_covered: list[str] = Field(default_factory=list)
    preferred_skills_missing: list[str] = Field(default_factory=list)
    project_relevance_score: int
    project_relevance_notes: str = ""
    experience_relevance_score: int
    experience_relevance_notes: str = ""
    education_match_score: int
    education_match_notes: str = ""
    missing_keywords: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)


class JobFitAnalysis(BaseModel):
    success: bool
    message: str
    optimized_projects: list[OptimizedProject] = Field(default_factory=list)
    ats_score: Optional[ATSScore] = None


class JobFeedbackRequest(BaseModel):
    vote: Literal["up", "down"]


class GithubSyncRequest(BaseModel):
    user_id: str


class GithubSyncResult(BaseModel):
    """What one manual "Sync now" run changed, for the button to report back."""

    success: bool
    message: str
    # None when the sync could not run at all (no linked account, GitHub
    # unreachable), which the UI must not present as "0 repos found".
    repo_count: Optional[int] = None
    added: int = 0
    removed: int = 0
    unlinked: int = 0
    renamed: int = 0
    total_projects: int = 0
    changed: bool = False
    synced_at: Optional[str] = None
