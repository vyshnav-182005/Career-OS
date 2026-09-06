from fastapi import APIRouter, BackgroundTasks, Depends, Query, HTTPException
from typing import List, Optional
import logging
import time

from backend.models.job import JobFilter, IngestionStatistics
from backend.services.job_ingestion import JobIngestionWorkflow
from backend.services.job_providers.registry import build_providers
from backend.db.supabase_client import (
    get_ats_scores_for_jobs,
    get_jobs_by_filter,
    get_profile_data,
    get_cached_profile_embedding,
    match_jobs,
    upsert_job_feedback,
)
from backend.services.embeddings import generate_profile_embedding
from backend.services.job_matching import retrieve_candidates
from backend.agents.job_matching_agent import rank_jobs, select_top_matches, TOP_CANDIDATES
from backend.services.ats_scoring import build_job_ats_summaries
from backend.services.job_fit_analysis import analyze_job_fit, JobNotFoundError, ProfileNotFoundError
from backend.models.schemas import JobFitAnalysis, JobFeedbackRequest
from backend.security import verify_internal_request

logger = logging.getLogger(__name__)

router = APIRouter(prefix='/jobs', tags=['Jobs'])

# Driven by JOB_PROVIDERS in backend/.env - see job_providers/registry.py
CONFIGURED_PROVIDERS = build_providers()

# Cosine similarity floor for /jobs/recommended matches. Below this, a job is
# not considered relevant enough to surface rather than merely "less similar".
MATCH_THRESHOLD = 0.45

# How many ranked matches /jobs/recommended returns by default. The Jobs page
# shows 10 per page and paginates client-side over this set, so the default is
# a few pages' worth: ranking the whole candidate pool is one request either
# way, and paging through it must not refire the LLM re-ranker.
DEFAULT_RECOMMENDED_LIMIT = 30
MAX_RECOMMENDED_LIMIT = 50

# How many jobs the Jobs page shows for "your top matches". The page is a
# single ranked list rather than a paginated feed, so this is deliberately the
# whole list - not a page size.
TOP_MATCHES_LIMIT = 10

# Search pulls a wider candidate pool than it returns, scores every candidate
# against the profile, and returns the best. Without this the page would be
# ranked by posted_date and the match score on each card would be decoration
# rather than an ordering.
SEARCH_CANDIDATE_POOL = 60
DEFAULT_SEARCH_LIMIT = 20
MAX_SEARCH_LIMIT = 50

# Debounces background ingestion per user so rapid dashboard re-renders/polling
# don't refire external API calls for the same preferred roles.
_INGESTION_DEBOUNCE_SECONDS = 600
_last_ingestion_trigger: dict[str, float] = {}
# Same idea, keyed by search term rather than user: two people searching
# "data scientist" a minute apart shouldn't both trigger a provider fan-out.
_last_query_ingestion: dict[str, float] = {}


def _background_ingest_for_roles(user_id: str, preferred_roles: list) -> None:
    """
    Fetches jobs for each preferred role from external providers. Runs as a
    BackgroundTask so it never blocks the /jobs/recommended response.
    """
    now = time.time()
    last_run = _last_ingestion_trigger.get(user_id, 0)
    if now - last_run < _INGESTION_DEBOUNCE_SECONDS:
        return
    _last_ingestion_trigger[user_id] = now

    for role_entry in preferred_roles:
        role_title = role_entry.get("title") if isinstance(role_entry, dict) else getattr(role_entry, "title", None)
        if not role_title:
            continue
        try:
            workflow = JobIngestionWorkflow(providers=CONFIGURED_PROVIDERS)
            workflow.run(query=role_title)
        except Exception as e:
            logger.warning("Background ingestion failed for role '%s': %s", role_title, e)


def _background_ingest_for_query(query: str) -> None:
    """
    Fetches jobs matching a user's search term from the external providers.

    Search reads the local jobs table, so a role nobody has ingested yet
    returns nothing. Rather than making the user wait on a provider fan-out,
    the search responds immediately from what's stored and this runs after, so
    the same search a moment later is populated. Debounced per term.
    """
    normalized = (query or "").strip().lower()
    if not normalized:
        return

    now = time.time()
    if now - _last_query_ingestion.get(normalized, 0) < _INGESTION_DEBOUNCE_SECONDS:
        return
    _last_query_ingestion[normalized] = now

    try:
        JobIngestionWorkflow(providers=CONFIGURED_PROVIDERS).run(query=query)
    except Exception as e:
        logger.warning("Background ingestion failed for search '%s': %s", query, e)


@router.post("/ingest", response_model=IngestionStatistics, summary="Trigger Job Ingestion Workflow")
def trigger_job_ingestion():
    """
    Manually triggers the ingestion workflow to fetch jobs from all configured providers,
    normalize, deduplicate, and upsert them into the database.
    """
    workflow = JobIngestionWorkflow(providers=CONFIGURED_PROVIDERS)
    stats = workflow.run()
    return stats

@router.get(
    "/recommended",
    summary="Get Recommended Jobs based on User Profile",
    dependencies=[Depends(verify_internal_request)],
)
async def get_recommended_jobs(
    user_id: str,
    background_tasks: BackgroundTasks,
    legacy: bool = Query(False, description="Use the pre-Phase-2 single-vector-kNN path"),
    limit: int = Query(
        DEFAULT_RECOMMENDED_LIMIT,
        ge=1,
        le=MAX_RECOMMENDED_LIMIT,
        description="Maximum matches to return; the client paginates over this set",
    ),
):
    """
    Returns jobs matched against the user's profile via hybrid retrieval
    (vector + lexical + title-family, hard-gated by role_family), then
    verified/re-ranked by the Job Matching Agent (LLM), which catches
    near-misses retrieval can't see and reports missing skills per job.
    Ingestion of fresh jobs for the user's preferred roles is kicked off as a
    background task so it never blocks this response.

    Every match carries an `ats_match_score` (0-100) for its card: the real
    LLM-backed score when this job has already been analyzed, otherwise a
    deterministic estimate from the same retrieval features used to rank it.

    ?legacy=true runs the pre-Phase-2 single-vector-kNN path unchanged, kept
    as a rollback escape hatch for one release.
    """
    profile_data = get_profile_data(user_id)
    if not profile_data:
        raise HTTPException(status_code=404, detail="Profile not found")

    preferred_roles = profile_data.get("preferred_job_roles", [])
    background_tasks.add_task(_background_ingest_for_roles, user_id, preferred_roles)

    if legacy:
        # Use the embedding cached at profile-intelligence time; only recompute
        # (expensive SentenceTransformer encode) for profiles created before caching existed.
        profile_embedding = get_cached_profile_embedding(user_id)
        if not profile_embedding:
            profile_embedding = generate_profile_embedding(profile_data)

        if not profile_embedding:
            logger.warning("Profile embedding unavailable for user %s, returning unranked active jobs", user_id)
            fallback_jobs = get_jobs_by_filter(JobFilter(), limit=15)
            return {"success": True, "data": fallback_jobs}

        matched_jobs = match_jobs(profile_embedding, match_threshold=MATCH_THRESHOLD, match_count=40)
        return {"success": True, "data": matched_jobs, "total": len(matched_jobs)}

    scored_jobs = retrieve_candidates(user_id, profile_data)
    if scored_jobs is None:
        # Embedding generation failed. Unlike the legacy path, this never
        # backfills with unfiltered active jobs - that fallback is exactly the
        # contamination bug this rework removes. The frontend already treats
        # a missing/empty `data` as its existing empty state.
        logger.warning("Profile embedding unavailable for user %s", user_id)
        return {"success": False, "data": [], "total": 0, "error": "embedding_unavailable"}

    ranked_jobs = await rank_jobs(user_id, scored_jobs[:TOP_CANDIDATES], profile_data, background_tasks)
    top_matches = select_top_matches(ranked_jobs, top_n=limit)

    entries = [ranked_job.model_dump() for ranked_job in top_matches]
    job_ids = [entry["job"]["id"] for entry in entries if entry.get("job", {}).get("id")]
    entries = build_job_ats_summaries(
        profile_data, entries, cached_scores=get_ats_scores_for_jobs(user_id, job_ids)
    )
    # An empty result here is almost always cold start rather than "no work
    # exists for you": ingestion for this user's roles was queued above as a
    # background task, so it runs *after* this response is sent. The first
    # candidate from a field nobody has signed up for yet therefore sees an
    # empty page even though their jobs are being fetched right then. Telling
    # the client that lets it say so and come back for the results, instead of
    # rendering a dead end the user has to reload out of.
    return {
        "success": True,
        "data": entries,
        "total": len(entries),
        "sourcing": not entries,
    }


@router.get(
    "/search",
    summary="Search active jobs, scored against the user's profile",
    dependencies=[Depends(verify_internal_request)],
)
def search_jobs(
    user_id: str,
    background_tasks: BackgroundTasks,
    q: str = Query("", description="Job title to search for; empty returns the newest active jobs"),
    limit: int = Query(DEFAULT_SEARCH_LIMIT, ge=1, le=MAX_SEARCH_LIMIT),
):
    """
    Title search over the stored jobs, returned in the same entry shape as
    /jobs/recommended - {job, ats_match_score, ats_score_source} - so the Jobs
    page renders one card design for both lists.

    Scoring is the deterministic no-LLM estimate (or the real score for a job
    the user already analyzed). Unlike /jobs/recommended this never calls the
    LLM re-ranker: a search should return as fast as the user types, and the
    ranking signal the estimate provides is enough to order a title match.

    Ingestion for the search term is kicked off as a background task, so a role
    that isn't in the table yet gets pulled in for next time.
    """
    query = (q or "").strip()

    # Score-then-truncate over a wider pool, so the returned list is genuinely
    # the best matches for the query rather than the most recently posted.
    candidates = get_jobs_by_filter(
        JobFilter(title=query or None),
        limit=max(SEARCH_CANDIDATE_POOL, limit),
    )

    entries: list[dict] = [{"job": job} for job in candidates]

    profile_data = get_profile_data(user_id)
    if profile_data and entries:
        job_ids = [entry["job"]["id"] for entry in entries if entry["job"].get("id")]
        entries = build_job_ats_summaries(
            profile_data, entries, cached_scores=get_ats_scores_for_jobs(user_id, job_ids)
        )
        entries.sort(key=lambda entry: entry.get("ats_match_score") or 0, reverse=True)

    if query:
        background_tasks.add_task(_background_ingest_for_query, query)

    entries = entries[:limit]
    return {"success": True, "data": entries, "total": len(entries)}


@router.post(
    "/{job_id}/analyze",
    response_model=JobFitAnalysis,
    summary="Analyze job fit: optimized project bullets + ATS score",
    dependencies=[Depends(verify_internal_request)],
)
async def analyze_job_fit_endpoint(job_id: str, user_id: str, force_refresh: bool = False):
    """
    Fast, synchronous job-fit analysis (no PDF rendering): job-specific optimized
    project bullets plus an ATS fit score. Cached per (user, job) and reused
    unless the profile has changed since or force_refresh is set.
    """
    try:
        return await analyze_job_fit(user_id, job_id, force_refresh=force_refresh)
    except JobNotFoundError:
        raise HTTPException(status_code=404, detail="Job not found")
    except ProfileNotFoundError:
        raise HTTPException(status_code=404, detail="Profile not found")


@router.post(
    "/{job_id}/feedback",
    summary="Record thumbs up/down feedback on a recommended job",
    dependencies=[Depends(verify_internal_request)],
)
def submit_job_feedback(job_id: str, user_id: str, payload: JobFeedbackRequest):
    """
    Persists a thumbs up/down vote for a (user, job) pair. Re-voting overwrites
    the previous vote. Used to gather signal on the Phase 2/3 ranking quality.
    """
    if not upsert_job_feedback(user_id, job_id, payload.vote):
        raise HTTPException(status_code=500, detail="Failed to record feedback")
    return {"success": True}


@router.get("", summary="Get Active Jobs")
def get_jobs(
    title: Optional[str] = Query(None, description="Filter by job title"),
    company: Optional[str] = Query(None, description="Filter by company name"),
    location: Optional[str] = Query(None, description="Filter by location"),
    employment_type: Optional[str] = Query(None, description="Filter by employment type"),
    skills: Optional[List[str]] = Query(None, description="Filter by skills"),
    limit: int = Query(20, ge=1, le=50, description="Page size"),
    offset: int = Query(0, ge=0, description="Page offset"),
):
    """
    Retrieves active jobs, optionally filtering by various attributes. Paginated.
    """
    filter_params = JobFilter(
        title=title,
        company=company,
        location=location,
        employment_type=employment_type,
        skills=skills
    )

    jobs = get_jobs_by_filter(filter_params, limit=limit, offset=offset)
    return {"success": True, "data": jobs, "limit": limit, "offset": offset}
