import asyncio
import logging
from typing import Any, Dict, Optional

from backend.models.resume import ParsedResume
from backend.models.schemas import ATSScore, JobFitAnalysis
from backend.agents.resume_optimization_agent import run_resume_optimization
from backend.services.job_context import resolve_job_text
from backend.services.ats_scoring import compute_ats_score, extract_optimized_projects
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

    # Whichever pieces are missing are independent LLM calls -- run them
    # concurrently (scheduled as tasks immediately) rather than one after another,
    # since this endpoint's whole point is to be fast enough to run on modal open.
    resume_task = None if optimized_resume is not None else asyncio.ensure_future(
        run_resume_optimization(user_id, job_title, job_description)
    )
    ats_task = None if ats_score is not None else asyncio.ensure_future(
        compute_ats_score(profile_data, job_title, job_description)
    )

    if resume_task is not None:
        optimized_resume = await resume_task
    if ats_task is not None:
        ats_score = await ats_task

    if not optimized_resume:
        return JobFitAnalysis(
            success=False,
            message="Failed to analyze job fit. Check logs for details.",
        )

    original_projects = profile_data.get("original_resume", {}).get("projects", [])
    optimized_projects = extract_optimized_projects(original_projects, optimized_resume.projects)

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
