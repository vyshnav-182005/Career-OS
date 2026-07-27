"""
Profile Intelligence Models — enriched career profile schemas.

These models represent the output of the Profile Intelligence Agent,
which analyzes a parsed resume to infer job roles, career level,
skill categories, and profile completeness.
"""

from pydantic import BaseModel, Field
from backend.models.resume import ParsedResume


class InferredJobRole(BaseModel):
    title: str
    confidence: str = Field(description="High, Medium, or Low")
    reasoning: str


class ProfileIntelligence(BaseModel):
    """Unified profile JSON stored in the database."""
    original_resume: ParsedResume
    preferred_job_roles: list[InferredJobRole] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    insights: list[str] = Field(default_factory=list)
