import asyncio
import json
import logging
import re
from openai import APITimeoutError, OpenAI

from backend.config import settings
from backend.db.supabase_client import get_profile_data
from backend.models.resume import ParsedResume

logger = logging.getLogger(__name__)

class ResumeOptimizationTimeoutError(Exception):
    """Raised when the resume optimization provider exceeds its timeout."""

RESUME_OPTIMIZATION_PROMPT = """\
You are an expert ATS Resume Optimization Agent. Your task is to tailor a candidate's resume to a specific Job Description (JD).

Given the base resume (in JSON) and the Job Description, you must output a new optimized resume JSON that matches the EXACT schema of the input resume.

Constraints:
1. STRICTLY NO HALLUCINATION: You may NOT invent new jobs, degrees, certifications, or skills that are not implied by the existing profile.
2. TAILORING: Rephrase existing bullet points and summaries to highlight experiences, skills, and projects most relevant to the JD keywords.
3. KEYWORDS: Ensure that keywords mentioned in the JD are naturally integrated into the resume content.
4. SELECTION: Select and prioritize the most relevant sentences, skills, and projects based on the user's stored data.
5. PROJECTS: For each project, keep only the 2-4 bullet points most relevant to the JD, reordered so the most relevant comes first. Drop projects that are clearly irrelevant to this JD rather than forcing a connection.
6. BULLET FORMAT: `projects[].description` and `experience[].responsibilities` MUST be JSON arrays of separate strings - one complete, self-contained sentence per element. Never return a single string containing list syntax, brackets, newlines, or leading "-"/"*"/"bullet" markers. Correct: ["Built X, cutting latency 40%.", "Led Y."]  Wrong: "['Built X', 'Led Y']".
7. COVERAGE: Carry through every section the base resume provides - education, skills, certifications, languages, publications and custom sections. Dropping a section only shortens the page; drop individual items only when they are genuinely irrelevant to this JD.
8. SUBSTANCE: Aim for roughly one full page of content: keep 3-4 bullets for each retained role and project, each a specific, quantified sentence drawn from the source material. Never pad with filler or generic claims the base resume does not support.
9. SCHEMA MATCHING: Return a JSON object matching the EXACT schema of the input (no markdown, no extra text).

Base Resume JSON:
{resume_json}

Job Title:
{job_title}

Job Description:
{job_description}

Return ONLY valid JSON matching the schema.
"""

async def run_resume_optimization(user_id: str, job_title: str, job_description: str) -> ParsedResume | None:
    logger.info("Starting Resume Optimization for user_id=%s, job_title=%s", user_id, job_title)
    
    profile_data = get_profile_data(user_id)
    if not profile_data:
        logger.error("No profile data found for user_id=%s", user_id)
        return None

    original_resume_data = profile_data.get("original_resume")
    if not original_resume_data:
        logger.error("No parsed resume found in profile data for user_id=%s", user_id)
        return None

    try:
        parsed_resume = ParsedResume(**original_resume_data)
    except Exception as e:
        logger.error("Failed to parse base resume data: %s", e)
        return None

    resume_dict = parsed_resume.model_dump()
    resume_dict.pop("raw_text", None)
    resume_json = json.dumps(resume_dict, indent=2)

    client = OpenAI(
        base_url="https://integrate.api.nvidia.com/v1",
        api_key=settings.nvidia_api_key,
        timeout=120.0,
        max_retries=1,
    )

    prompt = RESUME_OPTIMIZATION_PROMPT.format(
        resume_json=resume_json,
        job_title=job_title,
        job_description=job_description
    )

    def _call_llm():
        completion = client.chat.completions.create(
            model="meta/llama-3.1-70b-instruct",
            messages=[
                {
                    "role": "system",
                    "content": "You are a Resume Optimization Agent. Always respond with valid JSON only, no markdown.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=4096,
            response_format={"type": "json_object"},
        )
        return completion.choices[0].message.content or ""

    try:
        response_text = await asyncio.to_thread(_call_llm)
    except APITimeoutError as e:
        logger.exception("NVIDIA LLM request timed out during resume optimization")
        raise ResumeOptimizationTimeoutError("Resume optimization provider request timed out.") from e

    try:
        cleaned = response_text.strip()
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        optimized_data = json.loads(cleaned)
    except Exception as e:
        logger.error("Failed to parse LLM response: %s", e)
        return None
    
    try:
        optimized_resume = ParsedResume(**optimized_data)
        return optimized_resume
    except Exception as e:
        logger.error("Verification Engine Failed (Schema mismatch): %s", e)
        return None
