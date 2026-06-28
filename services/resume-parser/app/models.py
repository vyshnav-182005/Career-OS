from pydantic import BaseModel, Field
from typing import Optional


class PersonalInfo(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    location: Optional[str] = None
    linkedin: Optional[str] = None
    github: Optional[str] = None
    website: Optional[str] = None
    summary: Optional[str] = None


class Education(BaseModel):
    institution: str
    degree: Optional[str] = None
    field_of_study: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    gpa: Optional[str] = None
    description: Optional[str] = None


class Experience(BaseModel):
    company: str
    title: str
    location: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    is_current: bool = False
    responsibilities: list[str] = Field(default_factory=list)


class Project(BaseModel):
    name: str
    description: Optional[str] = None
    technologies: list[str] = Field(default_factory=list)
    url: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None


class Certification(BaseModel):
    name: str
    issuer: Optional[str] = None
    date: Optional[str] = None
    expiry: Optional[str] = None
    credential_id: Optional[str] = None


class SkillCategory(BaseModel):
    category: str
    skills: list[str] = Field(default_factory=list)


class ParsedResume(BaseModel):
    personal_info: Optional[PersonalInfo] = None
    education: list[Education] = Field(default_factory=list)
    experience: list[Experience] = Field(default_factory=list)
    projects: list[Project] = Field(default_factory=list)
    certifications: list[Certification] = Field(default_factory=list)
    skills: list[SkillCategory] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    raw_text: Optional[str] = None


class ParseResponse(BaseModel):
    success: bool
    data: Optional[ParsedResume] = None
    error: Optional[str] = None
    filename: Optional[str] = None
    file_type: Optional[str] = None
