from typing import Any, Dict, Tuple

from backend.services.text_cleaning import clean_html_text


def resolve_job_text(job: Dict[str, Any]) -> Tuple[str, str]:
    """
    Builds the (job_title, job_description) pair used to prompt the resume
    optimization / ATS scoring agents from a jobs table row, folding the
    job's tagged skills into the description text so they're visible to the LLM.

    The description is stripped of provider HTML/entities first: markup noise
    burns prompt tokens and degrades the skill extraction the ATS score depends
    on, and the same clean text is what the job detail view shows the user.
    """
    job_title = job.get("title") or ""
    job_description = clean_html_text(job.get("description"))
    skills = job.get("skills") or []
    if skills:
        job_description = f"{job_description}\n\nRequired/preferred skills: {', '.join(skills)}"
    return job_title, job_description
