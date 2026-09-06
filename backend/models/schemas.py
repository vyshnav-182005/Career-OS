from pydantic import BaseModel, Field, field_validator
from typing import Any, Literal, Optional

from backend.models.resume import Certification, Publication, normalize_bullets

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


class ProjectDescriptionEdit(BaseModel):
    """One project's bullets as the editor last showed them."""

    name: str
    url: Optional[str] = None
    description: list[str]

    @field_validator("description", mode="before")
    @classmethod
    def _clean(cls, value: Any) -> list[str]:
        return normalize_bullets(value)

    @field_validator("description")
    @classmethod
    def _reject_empty(cls, value: list[str]) -> list[str]:
        # A project with no bullets cannot be used in a tailored resume, and
        # saving one silently is how it stays that way unnoticed. The editor
        # says so before this is ever reached; this is the same rule held at
        # the boundary, so it does not depend on the UI enforcing it.
        if not value:
            raise ValueError(
                "Add at least one line about this project so it can be used in "
                "tailored resumes."
            )
        return value


class ProfileEditRequest(BaseModel):
    """A save from the profile editor. Absent sections are left untouched."""

    user_id: str
    certifications: Optional[list[Certification]] = None
    publications: Optional[list[Publication]] = None
    project_descriptions: Optional[list[ProjectDescriptionEdit]] = None


class ProfileEditResult(BaseModel):
    success: bool
    message: str
    certifications: int = 0
    publications: int = 0
    projects_updated: int = 0
    # Named so the caller can say which edit did not land rather than
    # reporting a save that quietly dropped one.
    unmatched_projects: list[str] = Field(default_factory=list)


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
