export interface OptimizedProject {
  project_name: string;
  technologies: string[];
  original_bullets: string[];
  optimized_bullets: string[];
}

export interface ATSScore {
  overall_score: number;
  skill_match_pct: number;
  required_skills_covered: string[];
  required_skills_missing: string[];
  preferred_skills_covered: string[];
  preferred_skills_missing: string[];
  project_relevance_score: number;
  project_relevance_notes: string;
  experience_relevance_score: number;
  experience_relevance_notes: string;
  education_match_score: number;
  education_match_notes: string;
  missing_keywords: string[];
  suggestions: string[];
}

export interface JobFitAnalysis {
  success: boolean;
  message: string;
  optimized_projects: OptimizedProject[];
  ats_score: ATSScore | null;
}

export async function analyzeJobFit(jobId: string, forceRefresh = false): Promise<JobFitAnalysis> {
  const response = await fetch(`/api/jobs/${jobId}/analyze`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ forceRefresh }),
  });

  const data: JobFitAnalysis = await response.json();

  if (!response.ok) {
    throw new Error(data.message || `Failed to analyze job fit: ${response.statusText}`);
  }

  return data;
}
