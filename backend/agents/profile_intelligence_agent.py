import asyncio
import json
import logging
import re
from openai import OpenAI

from backend.config import settings
from backend.db.supabase_client import get_profile_data, update_profile_intelligence
from backend.models.profile import (
    ProfileIntelligence,
    InferredJobRole,
)
from backend.models.resume import ParsedResume

logger = logging.getLogger(__name__)


PROFILE_INTELLIGENCE_PROMPT = """\
You are a Profile Intelligence Agent. Analyze the candidate's resume and GitHub summary to identify their key strengths, suitable job roles, and career insights.

Return a JSON object matching this EXACT schema (no markdown, no extra text):
{
  "strengths": ["strength1", "strength2"],
  "preferred_job_roles": [
    {
      "title": "Job title",
      "confidence": "High | Medium | Low",
      "reasoning": "Brief explanation"
    }
  ],
  "insights": ["insight1", "insight2"]
}

Rules:
1. strengths: Extract only transferable professional strengths (2-5 words each). Deduplicate. Limit to 8-12.
2. preferred_job_roles: Infer suitable job roles with confidence levels and reasoning.
3. insights: Provide 3-5 actionable career insights or observations based on their combined resume and GitHub activity (e.g., "Strong open-source presence in TypeScript suggests readiness for senior frontend roles").
4. Return ONLY valid JSON.

Candidate Data:

Resume (Summary):
{resume_json}

GitHub Summary:
{github_summary}
"""

async def run_profile_intelligence(user_id: str):
    logger.info("Starting Profile Intelligence Agent for user_id=%s", user_id)
    profile_data = get_profile_data(user_id)
    if not profile_data:
        logger.error("No profile data found for user_id=%s", user_id)
        return

    original_resume_data = profile_data.get("original_resume")
    if not original_resume_data:
        logger.error("No parsed resume found in profile data for user_id=%s", user_id)
        return
        
    github_summary = profile_data.get("github_summary", "No GitHub data available.")

    parsed_resume = ParsedResume(**original_resume_data)

    # Build a lightweight summary of the resume for the LLM
    # We remove raw_text and projects to save massive amounts of tokens
    resume_dict = parsed_resume.model_dump()
    resume_dict.pop("raw_text", None)
    resume_dict.pop("projects", None)
    
    resume_json = json.dumps(resume_dict, indent=2)

    # Run LLM
    client = OpenAI(
        base_url="https://integrate.api.nvidia.com/v1",
        api_key=settings.nvidia_api_key,
        timeout=120.0,
        max_retries=1,
    )

    prompt = PROFILE_INTELLIGENCE_PROMPT.replace(
        "{resume_json}", resume_json
    ).replace(
        "{github_summary}", github_summary
    )

    def _call_llm():
        completion = client.chat.completions.create(
            model=settings.model,
            messages=[
                {
                    "role": "system",
                    "content": "You are a Profile Intelligence Agent. Always respond with valid JSON only, no markdown.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            max_tokens=4096,
            response_format={"type": "json_object"},
        )
        return completion.choices[0].message.content or ""

    response_text = await asyncio.to_thread(_call_llm)

    try:
        cleaned = response_text.strip()
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        data = json.loads(cleaned)
    except Exception as e:
        logger.error("Failed to parse LLM response: %s", e)
        return

    preferred_roles = [
        InferredJobRole(**r) for r in data.get("preferred_job_roles", [])
    ]

    profile_intelligence = ProfileIntelligence(
        original_resume=parsed_resume,
        preferred_job_roles=preferred_roles,
        strengths=data.get("strengths", []),
        insights=data.get("insights", [])
    )

    update_profile_intelligence(user_id, profile_intelligence)
    logger.info("Profile Intelligence Agent completed for user_id=%s", user_id)
