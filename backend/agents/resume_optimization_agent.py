import asyncio
import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from openai import APITimeoutError
from pydantic import ValidationError

from backend.config import settings
from backend.services.llm_client import NO_THINKING, build_client
from backend.agents.ats_scoring_agent import run_ats_scoring
from backend.db.supabase_client import get_job_fit_analysis, get_profile_data
from backend.models.resume import ParsedResume, Project
from backend.services.ats_scoring import _significant_words

logger = logging.getLogger(__name__)

class ResumeOptimizationTimeoutError(Exception):
    """Raised when the resume optimization provider exceeds its timeout."""

RESUME_OPTIMIZATION_PROMPT = """\
You are an expert ATS Resume Optimization Agent. Your task is to tailor a candidate's resume to a specific Job Description (JD).

Given the base resume (in JSON) and the Job Description, you must output a new optimized resume JSON that matches the EXACT schema of the input resume.

Constraints:
1. STRICTLY NO HALLUCINATION: A fact may be reordered, reworded, or quantified only with a number already present in the source. No fact, skill, tool, employer, degree, or outcome may be introduced that is not verbatim or paraphrastically present in the Base Resume JSON below.
2. TAILORING: Rephrase existing bullet points and summaries to highlight experiences, skills, and projects most relevant to the JD keywords.
3. KEYWORDS: The "Required keywords" and "Preferred keywords" lines below are an authoritative classification of this JD - treat them as the keyword list and do NOT re-derive keywords from the JD prose. Naturally integrate the required keywords the candidate genuinely has into the resume content first, then the preferred ones. Never assert a keyword the Base Resume does not support.
4. SELECTION: Select and prioritize the most relevant sentences, skills, and projects based on the user's stored data.
5. PROJECT COUNT & CONTENT: Select AT MOST {max_projects} projects total - the ones most relevant to this JD's required and preferred keywords - and omit every other project entirely, even if it is a solid project in general; a focused, targeted resume beats a complete one. For each kept project, keep only the 2-4 bullet points most relevant to the JD, reordered so the most relevant comes first.
6. BULLET FORMAT: `projects[].description` and `experience[].responsibilities` MUST be JSON arrays of separate strings - one complete, self-contained sentence per element. Never return a single string containing list syntax, brackets, newlines, or leading "-"/"*"/"bullet" markers. Correct: ["Built X, cutting latency 40%.", "Led Y."]  Wrong: "['Built X', 'Led Y']".
7. COVERAGE: Carry through every section the base resume provides - education, skills, certifications, languages, publications and custom sections. Dropping a section only shortens the page; drop individual items only when they are genuinely irrelevant to this JD.
8. SUBSTANCE: Aim for roughly one full page of content: keep 3-4 bullets for each retained role and project, each a specific, quantified sentence drawn from the source material. Never pad with filler or generic claims the base resume does not support.
9. SCHEMA MATCHING: Return a JSON object matching the EXACT schema of the input (no markdown, no extra text).
10. PROTECTED SECTIONS: Certifications and publications are exempt from the relevance-based selection in rules 5 and 7. They must NEVER be dropped for failing to match this JD's keywords. The only reason to drop one is that the one-page budget in rule 8 forces a cut - and then drop the least prestigious or oldest first, never at random.

Base Resume JSON:
{resume_json}

Job Title:
{job_title}

ATS keyword classification for this JD (authoritative - see rule 3):
Required keywords: {required_keywords}
Preferred keywords: {preferred_keywords}

Job Description:
{job_description}

Return ONLY valid JSON matching the schema.
"""

# Appended to the original prompt on the single schema-validation retry, so the
# model sees exactly what pydantic rejected instead of guessing a second time.
SCHEMA_RETRY_TEMPLATE = (
    "\n\nYour previous response failed schema validation with this error: {error}. "
    "Return corrected JSON matching the exact schema."
)

NO_KEYWORDS_PLACEHOLDER = "(classification unavailable - infer from the Job Description below)"

# Rule 5 asks the model to keep at most this many projects, but a count
# instruction is not guaranteed to be followed - this is the deterministic
# backstop that enforces it regardless of what the model actually returned.
MAX_RESUME_PROJECTS = 4


def _project_relevance_score(project: Project, jd_words: set) -> int:
    """Word-overlap between a project's own content and the JD, for ranking."""
    words: set = set()
    for bullet in project.description or []:
        words |= _significant_words(bullet)
    for tech in project.technologies or []:
        words |= _significant_words(tech)
    if project.name:
        words |= _significant_words(project.name)
    return len(words & jd_words)


def _enforce_project_cap(
    resume: ParsedResume,
    job_title: str,
    job_description: str,
    required: List[str],
    preferred: List[str],
) -> ParsedResume:
    """
    Keeps at most MAX_RESUME_PROJECTS projects, ranked by keyword overlap with
    the JD. A stable sort means projects the model scored equally keep the
    order it already prioritized them in (rule 5 asks for most-relevant-first),
    so this only reaches for its own ranking to break ties or when the model
    didn't trim the list at all.
    """
    if len(resume.projects) <= MAX_RESUME_PROJECTS:
        return resume

    jd_text = " ".join(
        [job_title or "", job_description or "", " ".join(required), " ".join(preferred)]
    )
    jd_words = _significant_words(jd_text)

    ranked = sorted(
        resume.projects,
        key=lambda p: _project_relevance_score(p, jd_words),
        reverse=True,
    )
    resume.projects = ranked[:MAX_RESUME_PROJECTS]
    return resume


def _dedupe(values: Any) -> List[str]:
    """Order-preserving dedupe of a skill list, dropping blanks and non-strings."""
    cleaned = [str(v).strip() for v in (values or []) if v and str(v).strip()]
    return list(dict.fromkeys(cleaned))


def keywords_from_ats_score(ats_score: Optional[Dict[str, Any]]) -> Tuple[List[str], List[str]]:
    """
    Recovers the JD's required/preferred skill classification from a stored ATSScore.

    ATSScore doesn't keep the raw lists, but `*_covered` + `*_missing` is exactly
    the partition of them that services/ats_scoring.py built, so a cached score
    yields the same keywords without paying for a second classification call.
    """
    score = ats_score or {}
    required = _dedupe(
        list(score.get("required_skills_covered") or [])
        + list(score.get("required_skills_missing") or [])
    )
    preferred = _dedupe(
        list(score.get("preferred_skills_covered") or [])
        + list(score.get("preferred_skills_missing") or [])
    )
    return required, preferred


async def _resolve_jd_keywords(
    user_id: str,
    job_id: Optional[str],
    profile_data: Dict[str, Any],
    job_title: str,
    job_description: str,
    required_skills: Optional[List[str]],
    preferred_skills: Optional[List[str]],
) -> Tuple[List[str], List[str]]:
    """
    Returns this JD's (required, preferred) skills, spending as little as possible:

    1. Whatever the caller already has in hand - job_fit_analysis runs ATS scoring
       itself and passes its classification straight through.
    2. The ATS score cached per (user_id, job_id) by an earlier "Analyze fit".
    3. Only as a last resort, a fresh ATS classification call.

    An unavailable classification is not fatal: the prompt falls back to telling
    the model to infer keywords from the JD text.
    """
    if required_skills is not None or preferred_skills is not None:
        return _dedupe(required_skills), _dedupe(preferred_skills)

    if job_id:
        try:
            cached = get_job_fit_analysis(user_id, job_id)
        except Exception:
            logger.warning("Failed to read cached ATS score for user_id=%s job_id=%s", user_id, job_id)
            cached = None
        required, preferred = keywords_from_ats_score((cached or {}).get("ats_score"))
        if required or preferred:
            logger.info(
                "Reusing cached ATS keyword classification for user_id=%s job_id=%s", user_id, job_id
            )
            return required, preferred

    llm_result = await run_ats_scoring(profile_data, job_title, job_description)
    if not llm_result:
        logger.warning("ATS keyword classification unavailable for job_title=%s", job_title)
        return [], []
    return _dedupe(llm_result.get("required_skills")), _dedupe(llm_result.get("preferred_skills"))


def _parse_json_response(response_text: str) -> Any:
    cleaned = response_text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    return json.loads(cleaned)


async def run_resume_optimization(
    user_id: str,
    job_title: str,
    job_description: str,
    job_id: str | None = None,
    required_skills: List[str] | None = None,
    preferred_skills: List[str] | None = None,
) -> ParsedResume | None:
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

    # The ATS agent has already classified this JD's skills (or will, once, here)
    # - the optimizer reuses that instead of re-deriving keywords from JD prose.
    required, preferred = await _resolve_jd_keywords(
        user_id, job_id, profile_data, job_title, job_description, required_skills, preferred_skills
    )

    client = build_client(timeout=120.0)

    prompt = RESUME_OPTIMIZATION_PROMPT.format(
        resume_json=resume_json,
        job_title=job_title,
        required_keywords=", ".join(required) if required else NO_KEYWORDS_PLACEHOLDER,
        preferred_keywords=", ".join(preferred) if preferred else NO_KEYWORDS_PLACEHOLDER,
        job_description=job_description,
        max_projects=MAX_RESUME_PROJECTS,
    )

    def _call_llm(user_prompt: str):
        completion = client.chat.completions.create(
            # Was meta/llama-3.1-70b-instruct, retired by NVIDIA along with the
            # rest of the llama-3.1 family; settings.model is now itself a large
            # model, so this no longer needs to differ from the other agents.
            model=settings.model,
            messages=[
                {
                    "role": "system",
                    "content": "You are a Resume Optimization Agent. Always respond with valid JSON only, no markdown.",
                },
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.1,
            max_tokens=4096,
            response_format={"type": "json_object"},
            extra_body=NO_THINKING,
        )
        return completion.choices[0].message.content or ""

    try:
        response_text = await asyncio.to_thread(_call_llm, prompt)
    except APITimeoutError as e:
        logger.exception("NVIDIA LLM request timed out during resume optimization")
        raise ResumeOptimizationTimeoutError("Resume optimization provider request timed out.") from e

    try:
        optimized_data = _parse_json_response(response_text)
    except Exception as e:
        logger.error("Failed to parse LLM response: %s", e)
        return None

    try:
        optimized_resume = ParsedResume(**optimized_data)
    except ValidationError as validation_error:
        # One retry: the model usually fixes a schema slip once it's shown the
        # exact pydantic error, which is far cheaper than discarding the run.
        # (Bound to a local here because Python unbinds `validation_error`
        # itself as soon as the except block ends.)
        validation_error_text = str(validation_error)
        logger.warning(
            "Verification Engine Failed (Schema mismatch), retrying once: %s", validation_error_text
        )
    except Exception as e:
        logger.error("Verification Engine Failed (Schema mismatch): %s", e)
        return None
    else:
        return _enforce_project_cap(optimized_resume, job_title, job_description, required, preferred)

    retry_prompt = prompt + SCHEMA_RETRY_TEMPLATE.format(error=validation_error_text)

    try:
        retry_text = await asyncio.to_thread(_call_llm, retry_prompt)
    except APITimeoutError as e:
        logger.exception("NVIDIA LLM request timed out during resume optimization retry")
        raise ResumeOptimizationTimeoutError("Resume optimization provider request timed out.") from e

    try:
        retry_data = _parse_json_response(retry_text)
    except Exception as e:
        logger.error("Failed to parse LLM retry response: %s", e)
        return None

    try:
        retry_resume = ParsedResume(**retry_data)
    except Exception as e:
        logger.error("Verification Engine Failed after retry (Schema mismatch): %s", e)
        return None
    else:
        return _enforce_project_cap(retry_resume, job_title, job_description, required, preferred)
