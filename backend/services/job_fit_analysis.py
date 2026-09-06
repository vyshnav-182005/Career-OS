import logging
from typing import Any, Dict, Optional

from backend.models.resume import ParsedResume
from backend.models.schemas import ATSScore, JobFitAnalysis
from backend.agents.resume_optimization_agent import (
    keywords_from_ats_score,
    run_resume_optimization,
)
from backend.services.job_context import resolve_job_text
from backend.services.ats_scoring import (
    compute_ats_score,
    extract_optimized_projects,
    log_optimization_skill_delta,
    verify_experience_grounding,
)
from backend.db.supabase_client import (
    get_job_by_id,
    get_profile_data,
    get_job_fit_analysis,
    get_profile_updated_at,
    upsert_ats_score,
    upsert_optimized_resume_snapshot,
)

logger = logging.getLogger(__name__)


class JobNotFoundError(Exception):
    """Raised when the referenced job_id doesn't exist."""


class ProfileNotFoundError(Exception):
    """Raised when the user has no parsed profile yet."""


def _cache_is_fresh(cached: Optional[Dict[str, Any]], profile_updated_at: Optional[str]) -> bool:
    if not cached:
        return False
    if not profile_updated_at:
        return True
    return cached.get("updated_at", "") >= profile_updated_at


async def analyze_job_fit(user_id: str, job_id: str, force_refresh: bool = False) -> JobFitAnalysis:
    """
    Produces job-specific optimized project bullets + an ATS fit score for a
    (user, job) pair. Reuses the existing Resume Optimization Agent as the
    source of tailored content rather than duplicating resume-rewriting logic;
    results are cached per (user, job) and reused unless the profile has since
    changed or a refresh is explicitly requested.
    """
    job = get_job_by_id(job_id)
    if not job:
        raise JobNotFoundError(f"Job {job_id} not found.")

    profile_data = get_profile_data(user_id)
    if not profile_data or not profile_data.get("original_resume"):
        raise ProfileNotFoundError("Profile not found. Upload a resume first.")

    job_title, job_description = resolve_job_text(job)

    cached = None if force_refresh else get_job_fit_analysis(user_id, job_id)
    profile_updated_at = get_profile_updated_at(user_id)
    fresh = _cache_is_fresh(cached, profile_updated_at)

    optimized_resume: Optional[ParsedResume] = None
    if fresh and cached.get("optimized_resume_json"):
        try:
            optimized_resume = ParsedResume(**cached["optimized_resume_json"])
        except Exception:
            logger.warning(
                "Cached optimized resume failed to parse for user_id=%s job_id=%s", user_id, job_id
            )

    ats_score: Optional[ATSScore] = None
    if fresh and cached.get("ats_score"):
        try:
            ats_score = ATSScore(**cached["ats_score"])
        except Exception:
            ats_score = None

    # These two used to run concurrently, but the optimizer now consumes the ATS
    # agent's required/preferred skill classification instead of re-deriving
    # keywords from the JD prose, so scoring has to land first. Its lists are
    # handed straight to the optimizer -- passing them (even empty, when scoring
    # failed) is what stops the agent from paying for a second classification.
    if ats_score is None:
        ats_score = await compute_ats_score(profile_data, job_title, job_description)

    if optimized_resume is None:
        required_skills, preferred_skills = keywords_from_ats_score(
            ats_score.model_dump() if ats_score else None
        )
        optimized_resume = await run_resume_optimization(
            user_id,
            job_title,
            job_description,
            job_id=job_id,
            required_skills=required_skills,
            preferred_skills=preferred_skills,
        )

    if not optimized_resume:
        return JobFitAnalysis(
            success=False,
            message="Failed to analyze job fit. Check logs for details.",
        )

    original_resume = profile_data.get("original_resume", {}) or {}
    original_projects = original_resume.get("projects", [])
    optimized_projects = extract_optimized_projects(original_projects, optimized_resume.projects)

    # Experience bullets get the same anti-hallucination check the project
    # bullets go through before anything is persisted or shown.
    optimized_resume.experience = verify_experience_grounding(
        original_resume.get("experience") or [], optimized_resume.experience
    )

    # Log-only feedback signal: did tailoring actually improve keyword coverage?
    log_optimization_skill_delta(optimized_resume.model_dump(), ats_score, user_id, job_id)

    try:
        upsert_optimized_resume_snapshot(
            user_id,
            job_id,
            optimized_resume.model_dump(),
            [p.model_dump() for p in optimized_projects],
        )
    except Exception:
        logger.warning(
            "Failed to persist optimized resume snapshot for user_id=%s job_id=%s", user_id, job_id
        )

    if ats_score:
        try:
            upsert_ats_score(user_id, job_id, ats_score.model_dump())
        except Exception:
            logger.warning("Failed to persist ATS score for user_id=%s job_id=%s", user_id, job_id)

    message = (
        "Job fit analysis complete."
        if ats_score
        else "Optimized project bullets ready; ATS scoring is temporarily unavailable."
    )

    return JobFitAnalysis(
        success=True,
        message=message,
        optimized_projects=optimized_projects,
        ats_score=ats_score,
    )
