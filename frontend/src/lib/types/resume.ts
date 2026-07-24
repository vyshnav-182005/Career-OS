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
  description: string[];
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

export interface Publication {
  title: string;
  publisher: string | null;
  date: string | null;
  url: string | null;
  description: string | null;
}

export interface CustomSectionItem {
  title: string | null;
  subtitle: string | null;
  date: string | null;
  description: string | null;
}

export interface CustomSection {
  section_title: string;
  items: CustomSectionItem[];
}

export interface ParsedResume {
  personal_info: PersonalInfo | null;
  education: Education[];
  experience: Experience[] | null;
  projects: Project[];
  certifications: Certification[];
  skills: SkillCategory[];
  languages: string[];
  publications: Publication[];
  custom_sections: CustomSection[];
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

export interface ProfileIntelligence {
  original_resume: ParsedResume;
  preferred_job_roles: InferredJobRole[];
  strengths: string[];
}

export interface PipelineResponse {
  success: boolean;
  parsed_resume: ParsedResume | null;
  profile_intelligence: ProfileIntelligence | null;
  error: string | null;
}
