"""
Profile Intelligence Agent — LLM-powered resume analysis.

Pipeline:
  1. Serialize a validated ParsedResume to JSON
  2. Send to NVIDIA NIM with a detailed analysis prompt
  3. Parse the LLM JSON response into ProfileIntelligence
  4. Return the enriched, validated model
"""

import json
import logging
import re

from openai import OpenAI

from app.config import get_settings
from app.models import ParsedResume
from app.profile_models import ProfileIntelligence

logger = logging.getLogger(__name__)

ANALYSIS_PROMPT = """\
You are a Profile Intelligence Agent.

Your role: Analyze the structured resume to build an enriched career profile. \
You infer suitable job roles, career level, skill categories, and profile \
completeness while preserving the user's original data.

Given the following parsed resume JSON, perform a deep analysis and return a \
JSON object matching this EXACT schema (no extra keys, no markdown, no \
explanatory text):

{{
  "inferred_job_roles": [
    {{
      "title": "Job title that fits this candidate",
      "confidence": "High, Medium, or Low",
      "reasoning": "Brief explanation of why this role fits"
    }}
  ],
  "career_level": "One of: Entry, Junior, Mid, Senior, Lead, Executive",
  "total_years_experience": 0.0,
  "skill_categories": [
    {{
      "category": "Category name (e.g. Programming Languages, Frameworks)",
      "skills": ["skill1", "skill2"],
      "proficiency_level": "One of: Beginner, Intermediate, Advanced, Expert"
    }}
  ],
  "profile_completeness": {{
    "overall_score": 0,
    "has_contact_info": true,
    "has_summary": false,
    "has_education": true,
    "has_experience": true,
    "has_skills": true,
    "has_projects": false,
    "has_certifications": false,
    "missing_sections": ["summary", "projects"],
    "improvement_suggestions": ["Add a professional summary", "Include projects"]
  }},
  "industry_domains": ["Technology", "Finance"],
  "key_strengths": ["Strong backend development", "Cloud infrastructure"],
  "professional_summary": "A concise 2-3 sentence professional summary"
}}

Rules:
- Return ONLY valid JSON. No markdown, no code fences, no explanatory text.
- Infer 2-5 suitable job roles ranked by confidence.
- Calculate total_years_experience from the experience dates.
- Group skills into meaningful categories with proficiency levels.
- Score profile_completeness.overall_score from 0-100 based on section coverage and depth.
- Identify 2-5 key strengths from the resume content.
- Write a compelling professional_summary even if the resume lacks one.
- Do NOT include an "original_resume" field in your response.

Parsed resume:
---
{resume_json}
---
"""


def _clean_json_response(response_text: str) -> str:
    """Strip markdown fences if the model wraps the JSON in them."""
    cleaned = re.sub(r"^```(?:json)?\s*", "", response_text.strip(), flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned.strip())
    return cleaned.strip()


def analyze_profile(parsed_resume: ParsedResume) -> ProfileIntelligence:
    """
    Analyze a parsed resume using NVIDIA NIM to produce enriched
    profile intelligence.

    Args:
        parsed_resume: A validated ParsedResume model from the parser.

    Returns:
        A ProfileIntelligence model containing the original resume
        plus LLM-inferred career insights.
    """
    settings = get_settings()

    # Serialize resume to JSON (exclude raw_text to save tokens)
    resume_data = parsed_resume.model_dump(exclude={"raw_text"})
    resume_json = json.dumps(resume_data, indent=2, default=str)

    logger.info("Sending parsed resume to NVIDIA NIM for profile analysis")

    # Build the NVIDIA NIM client (OpenAI-compatible)
    client = OpenAI(
        base_url="https://integrate.api.nvidia.com/v1",
        api_key=settings.nvidia_api_key,
        timeout=60.0,
    )

    prompt = ANALYSIS_PROMPT.format(resume_json=resume_json)

    completion = client.chat.completions.create(
        model="meta/llama-3.1-70b-instruct",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a Profile Intelligence Agent that analyzes resumes "
                    "and returns structured JSON profile data. Always respond "
                    "with valid JSON only, no markdown or explanatory text."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
        max_tokens=4096,
    )

    response_text = completion.choices[0].message.content or ""
    logger.info("Received profile analysis response (%d chars)", len(response_text))

    # Parse the LLM response
    cleaned = _clean_json_response(response_text)
    data = json.loads(cleaned)

    # Attach the original resume (not part of LLM output)
    data["original_resume"] = parsed_resume.model_dump()

    profile = ProfileIntelligence(**data)
    logger.info(
        "Profile analysis complete — career_level=%s, roles=%d, score=%d",
        profile.career_level,
        len(profile.inferred_job_roles),
        profile.profile_completeness.overall_score,
    )

    return profile
