"""
Profile Intelligence Models — enriched career profile schemas.

These models represent the output of the Profile Intelligence Agent,
which analyzes a parsed resume to infer job roles, career level,
skill categories, and profile completeness.
"""

from pydantic import BaseModel, Field
from typing import Optional
from app.models import ParsedResume


class InferredJobRole(BaseModel):
    title: str
    confidence: str = Field(description="High, Medium, or Low")
    reasoning: str


class SkillCategoryInference(BaseModel):
    category: str
    skills: list[str] = Field(default_factory=list)
    proficiency_level: str = Field(description="Beginner, Intermediate, Advanced, or Expert")


class ProfileCompleteness(BaseModel):
    overall_score: int = Field(ge=0, le=100)
    has_contact_info: bool = False
    has_summary: bool = False
    has_education: bool = False
    has_experience: bool = False
    has_skills: bool = False
    has_projects: bool = False
    has_certifications: bool = False
    missing_sections: list[str] = Field(default_factory=list)
    improvement_suggestions: list[str] = Field(default_factory=list)


class ProfileIntelligence(BaseModel):
    """Enriched profile — canonical data for downstream services and AI agents."""
    original_resume: ParsedResume
    inferred_job_roles: list[InferredJobRole] = Field(default_factory=list)
    career_level: str = Field(description="Entry, Junior, Mid, Senior, Lead, or Executive")
    total_years_experience: float = 0.0
    skill_categories: list[SkillCategoryInference] = Field(default_factory=list)
    profile_completeness: ProfileCompleteness
    industry_domains: list[str] = Field(default_factory=list)
    key_strengths: list[str] = Field(default_factory=list)
    professional_summary: str = ""
