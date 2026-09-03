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
    SearchIntent,
)
from backend.models.resume import ParsedResume
from backend.services.embeddings import generate_profile_embedding
from backend.services import taxonomy

logger = logging.getLogger(__name__)

_VALID_SENIORITY = {"intern", "junior", "mid", "senior", "lead"}
_VALID_WORK_MODE = {"onsite", "hybrid", "remote", "any"}

_ROLE_FAMILIES_LIST = ", ".join(taxonomy.ROLE_FAMILIES)

PROFILE_INTELLIGENCE_PROMPT = """\
You are a Profile Intelligence Agent. Analyze the candidate's resume and GitHub summary to identify their key strengths, suitable job roles, career insights, and a structured search intent.

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
  "insights": ["insight1", "insight2"],
  "search_intent": {
    "role_families": ["family-slug", "..."],
    "excluded_families": ["family-slug", "..."],
    "seniority": "intern | junior | mid | senior | lead",
    "must_have_skills": ["skill1", "skill2"],
    "nice_to_have_skills": ["skill3"],
    "locations": ["location1"],
    "work_mode": "onsite | hybrid | remote | any",
    "employment_types": ["full-time"]
  }
}

Rules:
1. strengths: Extract only transferable professional strengths (2-5 words each). Deduplicate. Limit to 8-12.
2. preferred_job_roles: Infer suitable job roles with confidence levels and reasoning.
3. insights: Provide 3-5 actionable career insights or observations based on their combined resume and GitHub activity (e.g., "Strong open-source presence in TypeScript suggests readiness for senior frontend roles").
4. search_intent.role_families: Pick ONLY from this fixed list of family slugs — never invent one:
   [FAMILY_LIST]
   Choose every family the résumé provides clear evidence for (usually 1-3).
5. search_intent.excluded_families: Pick from the SAME fixed list. This is a deliberate NEGATIVE
   signal — list every family the résumé shows NO evidence of, especially ones that could
   otherwise look superficially plausible (e.g. a backend engineer with some AWS mentions but no
   on-call/infra ownership should exclude "devops-sre"). This field is what later filtering relies
   on to keep unrelated roles out, so do not leave it empty unless the résumé genuinely spans
   almost every family.
6. search_intent.seniority: Derive from total years of professional experience visible in the
   résumé's experience dates (not internships alone) — roughly 0 years = intern, <2 = junior,
   2-5 = mid, 5-8 = senior, 8+ = lead.
7. search_intent.must_have_skills / nice_to_have_skills: Pull from the résumé's actual skills,
   experience, and projects — must-have are skills used repeatedly/recently, nice-to-have are
   skills seen once or in older projects.
8. Return ONLY valid JSON.

Candidate Data:

Resume (Summary):
{resume_json}

GitHub Summary:
{github_summary}
""".replace("[FAMILY_LIST]", _ROLE_FAMILIES_LIST)

def _build_search_intent(raw: dict | None) -> SearchIntent:
    """
    Validates and coerces the LLM's raw search_intent dict into a SearchIntent.
    Never trusts the LLM output shape directly: unknown family slugs are
    dropped, skill lists are canonicalised through the taxonomy, and enum
    fields fall back to a safe default rather than propagating garbage.
    """
    raw = raw or {}

    def _valid_families(values) -> list[str]:
        if not isinstance(values, list):
            return []
        return [f for f in values if f in taxonomy.ROLE_FAMILIES]

    def _str_list(values) -> list[str]:
        return [v for v in values if isinstance(v, str)] if isinstance(values, list) else []

    seniority = raw.get("seniority")
    if seniority not in _VALID_SENIORITY:
        seniority = "mid"

    work_mode = raw.get("work_mode")
    if work_mode not in _VALID_WORK_MODE:
        work_mode = "any"

    return SearchIntent(
        role_families=_valid_families(raw.get("role_families")),
        excluded_families=_valid_families(raw.get("excluded_families")),
        seniority=seniority,
        must_have_skills=taxonomy.canonicalize_skills(_str_list(raw.get("must_have_skills"))),
        nice_to_have_skills=taxonomy.canonicalize_skills(_str_list(raw.get("nice_to_have_skills"))),
        locations=_str_list(raw.get("locations")),
        work_mode=work_mode,
        employment_types=_str_list(raw.get("employment_types")),
    )


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

    search_intent = _build_search_intent(data.get("search_intent"))

    profile_intelligence = ProfileIntelligence(
        original_resume=parsed_resume,
        preferred_job_roles=preferred_roles,
        strengths=data.get("strengths", []),
        insights=data.get("insights", []),
        search_intent=search_intent,
    )

    # Cache the profile embedding now (the only place profile_data changes) so
    # /jobs/recommended never has to recompute it per-request.
    profile_embedding = generate_profile_embedding(profile_intelligence.model_dump())

    update_profile_intelligence(user_id, profile_intelligence, profile_embedding=profile_embedding)
    logger.info("Profile Intelligence Agent completed for user_id=%s", user_id)
