/**
 * TypeScript types mirroring the backend Pydantic models in
 * services/resume-parser/app/models.py
 */

export interface PersonalInfo {
  name: string | null;
  email: string | null;
  phone: string | null;
  location: string | null;
  linkedin: string | null;
  github: string | null;
  website: string | null;
  summary: string | null;
}

export interface Education {
  institution: string;
  degree: string | null;
  field_of_study: string | null;
  start_date: string | null;
  end_date: string | null;
  gpa: string | null;
  description: string | null;
}

export interface Experience {
  company: string;
  title: string;
  location: string | null;
  start_date: string | null;
  end_date: string | null;
  is_current: boolean;
  responsibilities: string[];
}

export interface Project {
  name: string;
  description: string | null;
  technologies: string[];
  url: string | null;
  start_date: string | null;
  end_date: string | null;
}

export interface Certification {
  name: string;
  issuer: string | null;
  date: string | null;
  expiry: string | null;
  credential_id: string | null;
}

export interface SkillCategory {
  category: string;
  skills: string[];
}

export interface ParsedResume {
  personal_info: PersonalInfo | null;
  education: Education[];
  experience: Experience[];
  projects: Project[];
  certifications: Certification[];
  skills: SkillCategory[];
  languages: string[];
  raw_text: string | null;
}

export interface ParseResponse {
  success: boolean;
  data: ParsedResume | null;
  error: string | null;
  filename: string | null;
  file_type: string | null;
}

export interface InferredJobRole {
  title: string;
  confidence: string;
  reasoning: string;
}

export interface SkillCategoryInference {
  category: string;
  skills: string[];
  proficiency_level: string;
}

export interface ProfileCompleteness {
  overall_score: number;
  has_contact_info: boolean;
  has_summary: boolean;
  has_education: boolean;
  has_experience: boolean;
  has_skills: boolean;
  has_projects: boolean;
  has_certifications: boolean;
  missing_sections: string[];
  improvement_suggestions: string[];
}

export interface ProfileIntelligence {
  original_resume: ParsedResume;
  inferred_job_roles: InferredJobRole[];
  career_level: string;
  total_years_experience: number;
  skill_categories: SkillCategoryInference[];
  profile_completeness: ProfileCompleteness;
  industry_domains: string[];
  key_strengths: string[];
  professional_summary: string;
}

export interface PipelineResponse {
  success: boolean;
  parsed_resume: ParsedResume | null;
  profile_intelligence: ProfileIntelligence | null;
  error: string | null;
}
