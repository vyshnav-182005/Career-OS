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


class SearchIntent(BaseModel):
    """
    Structured, machine-usable search intent derived from a résumé — the
    taxonomy every downstream job-matching filter will key off. Populated by
    the Profile Intelligence Agent and validated server-side against
    backend.services.taxonomy before being stored.
    """
    role_families: list[str] = Field(default_factory=list)
    excluded_families: list[str] = Field(default_factory=list)
    seniority: str = Field(default="mid", description="intern | junior | mid | senior | lead")
    must_have_skills: list[str] = Field(default_factory=list)
    nice_to_have_skills: list[str] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)
    work_mode: str = Field(default="any", description="onsite | hybrid | remote | any")
    employment_types: list[str] = Field(default_factory=list)


class ProfileIntelligence(BaseModel):
    """Unified profile JSON stored in the database."""
    original_resume: ParsedResume
    preferred_job_roles: list[InferredJobRole] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    insights: list[str] = Field(default_factory=list)
    search_intent: SearchIntent | None = None
