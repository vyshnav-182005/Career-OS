import asyncio
import json
import logging
import re
from typing import Any, Dict, Optional

from openai import APITimeoutError, OpenAI

from backend.config import settings

logger = logging.getLogger(__name__)

ATS_SCORING_PROMPT = """\
You are an ATS (Applicant Tracking System) analysis agent. Compare the candidate's \
profile against a job description and return a strict JSON analysis.

Return a JSON object matching EXACTLY this schema (no markdown, no extra text):
{{
  "required_skills": ["skill mentioned in the JD as required/must-have"],
  "preferred_skills": ["skill mentioned in the JD as preferred/nice-to-have/bonus"],
  "project_relevance_score": 0-100,
  "project_relevance_notes": "1-2 sentences",
  "experience_relevance_score": 0-100,
  "experience_relevance_notes": "1-2 sentences",
  "education_match_score": 0-100,
  "education_match_notes": "1-2 sentences",
  "suggestions": ["actionable suggestion 1", "actionable suggestion 2"]
}}

Rules:
1. required_skills / preferred_skills: read the job description and classify every \
skill, tool, or technology it mentions as required (explicitly required, must-have, \
"X+ years of ...") or preferred (nice-to-have, bonus, "a plus"). Use the skill names \
as they appear in the JD, deduplicated.
2. project_relevance_score: how relevant the candidate's projects (given below) are \
to this job's responsibilities, based only on the provided project data.
3. experience_relevance_score: how relevant the candidate's work/internship \
experience is to this job, based only on the provided experience data.
4. education_match_score: how well the candidate's education/certifications match \
the job's stated qualifications (use 100 if the JD states no specific requirement).
5. suggestions: 3-5 concrete, actionable ways the candidate could improve their fit \
for THIS specific job, based only on gaps visible in the provided data (e.g. \
"Emphasize your X project", "Add measurable outcomes to your Y experience"). Never \
suggest fabricating skills, experience, or credentials.
6. Do not invent skills, projects, or experience for the candidate beyond what is in \
the provided data.
7. Return ONLY valid JSON.

Candidate Profile:
{profile_summary}

Job Title:
{job_title}

Job Description:
{job_description}
"""


def _build_profile_summary(profile_data: Dict[str, Any]) -> str:
    original = (profile_data or {}).get("original_resume", {}) or {}

    summary = {
        "strengths": (profile_data or {}).get("strengths", []),
        "preferred_roles": [
            r.get("title") for r in (profile_data or {}).get("preferred_job_roles", []) if isinstance(r, dict)
        ],
        "education": [
            {
                "institution": e.get("institution"),
                "degree": e.get("degree"),
                "field_of_study": e.get("field_of_study"),
            }
            for e in original.get("education", [])
        ],
        "experience": [
            {
                "title": e.get("title"),
                "company": e.get("company"),
                "responsibilities": e.get("responsibilities", [])[:5],
            }
            for e in original.get("experience", [])
        ],
        "projects": [
            {
                "name": p.get("name"),
                "technologies": p.get("technologies", []),
                "description": p.get("description", [])[:5],
            }
            for p in original.get("projects", [])
        ],
        "certifications": [c.get("name") for c in original.get("certifications", [])],
        "skills": [
            {"category": c.get("category"), "skills": c.get("skills", [])}
            for c in original.get("skills", [])
        ],
    }
    return json.dumps(summary, indent=2)


async def run_ats_scoring(
    profile_data: Dict[str, Any], job_title: str, job_description: str
) -> Optional[Dict[str, Any]]:
    """
    Asks the LLM to classify the JD's required/preferred skills and score the
    qualitative fit dimensions (project/experience/education relevance) plus
    suggestions. Deterministic skill-coverage math and the final overall score
    are computed separately in services/ats_scoring.py.
    """
    logger.info("Starting ATS scoring for job_title=%s", job_title)

    profile_summary = _build_profile_summary(profile_data)

    client = OpenAI(
        base_url="https://integrate.api.nvidia.com/v1",
        api_key=settings.nvidia_api_key,
        timeout=90.0,
        max_retries=1,
    )

    prompt = ATS_SCORING_PROMPT.format(
        profile_summary=profile_summary,
        job_title=job_title,
        job_description=job_description,
    )

    def _call_llm():
        completion = client.chat.completions.create(
            model=settings.model,
            messages=[
                {
                    "role": "system",
                    "content": "You are an ATS Scoring Agent. Always respond with valid JSON only, no markdown.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=2048,
            response_format={"type": "json_object"},
        )
        return completion.choices[0].message.content or ""

    try:
        response_text = await asyncio.to_thread(_call_llm)
    except APITimeoutError:
        logger.exception("NVIDIA LLM request timed out during ATS scoring")
        return None

    try:
        cleaned = response_text.strip()
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        return json.loads(cleaned)
    except Exception:
        logger.error("Failed to parse ATS scoring LLM response")
        return None
