from fastapi import APIRouter, BackgroundTasks, Depends, Query, HTTPException
from typing import List, Optional
from concurrent.futures import ThreadPoolExecutor
import asyncio
import logging
import threading
import time

from backend.models.job import JobFilter, IngestionStatistics
from backend.services.job_ingestion import JobIngestionWorkflow
from backend.services.job_providers.registry import build_providers
from backend.db.supabase_client import (
    get_ats_scores_for_jobs,
    get_jobs_by_filter,
    get_profile_data,
    get_profile_version,
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


# Ingestion runs on one dedicated worker rather than wherever each background
# task happens to land.
#
# Every distinct search term starts its own JobIngestionWorkflow, and they used
# to overlap freely - five concurrent runs from a handful of searches, measured
# - each fanning out across the seeded ATS boards and embedding what it found.
# That competes for CPU and sockets with the very requests that triggered it:
# /jobs/search swung between 1.3s and 10.3s purely on how many runs were in
# flight. Serialising them costs nothing, since none of this is on the request
# path, and takes that variance out of what the user waits for.
_INGESTION_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="job-ingest")
# Ceiling on the backlog so a burst of distinct search terms can't queue an
# unbounded amount of work. Dropping a run is safe: the term simply stays
# un-ingested until it is searched again after the debounce window, and the
# 6-hourly scheduled sync covers the whole table regardless.
_MAX_QUEUED_INGESTIONS = 4
_queued_ingestions = 0
_queue_lock = threading.Lock()
# Breathing room between consecutive runs. A queue that runs back to back is
# still continuous load on the same Supabase connection and CPU the request
# path needs - searching several new terms in a row was enough to push
# /jobs/search from 1.1s to 6.2s. Spacing the runs keeps every queued term (so
# the "sourcing that role now" promise still holds) while leaving gaps the
# request path can use. Nobody is waiting on this, so the delay is free.
_INGESTION_COOLDOWN_SECONDS = 30


def _submit_ingestion(fn, *args) -> bool:
    """
    Queues one ingestion run on the single ingestion worker. Returns False if
    the backlog is already at _MAX_QUEUED_INGESTIONS and the run was dropped,
    so the caller can release its debounce entry rather than suppressing the
    term for the full window on work that never happened.
    """
    global _queued_ingestions
    with _queue_lock:
        if _queued_ingestions >= _MAX_QUEUED_INGESTIONS:
            logger.info("Ingestion backlog at %d; dropping this run.", _queued_ingestions)
            return False
        queued_ahead = _queued_ingestions
        _queued_ingestions += 1

    def _run() -> None:
        global _queued_ingestions
        try:
            # Only wait when something else just ran; the first run of a quiet
            # period starts immediately, so a single search is served as
            # promptly as it always was.
            if queued_ahead:
                time.sleep(_INGESTION_COOLDOWN_SECONDS)
            fn(*args)
        except Exception:
            logger.exception("Ingestion run failed")
        finally:
            with _queue_lock:
                _queued_ingestions -= 1

    _INGESTION_EXECUTOR.submit(_run)
    return True


def _debounced(store: dict[str, float], key: str, now: float) -> bool:
    """
    Records `key` as triggered at `now` and reports whether it was already
    within the debounce window (True = caller should skip this run).

    Entries older than the window carry no information - the next check on that
    key passes regardless - so they are dropped here rather than accumulating.
    Search terms are user-supplied and unbounded in variety, so without this the
    dict grows for the life of the process. Note both stores are per-process:
    the debounce does not survive a restart and is not shared across workers,
    which is acceptable for something whose only job is suppressing duplicate
    background fetches.
    """
    cutoff = now - _INGESTION_DEBOUNCE_SECONDS
    recent = store.get(key, 0) > cutoff
    for stale in [k for k, seen in store.items() if seen <= cutoff]:
        del store[stale]
    if not recent:
        store[key] = now
    return recent


def _background_ingest_for_roles(user_id: str, preferred_roles: list) -> None:
    """
    Fetches jobs for each preferred role from external providers. Runs as a
    BackgroundTask so it never blocks the /jobs/recommended response.
    """
    if _debounced(_last_ingestion_trigger, user_id, time.time()):
        return
    if not _submit_ingestion(_ingest_roles, preferred_roles):
        _last_ingestion_trigger.pop(user_id, None)


def _ingest_roles(preferred_roles: list) -> None:
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

    if _debounced(_last_query_ingestion, normalized, time.time()):
        return
    if not _submit_ingestion(_ingest_query, query):
        # The run never happened, so don't hold the term's debounce against a
        # user who searches it again - the Jobs page has just told them we
        # started sourcing it.
        _last_query_ingestion.pop(normalized, None)


def _ingest_query(query: str) -> None:
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
    # Every DB call in this handler is a blocking client, and this is an async
    # endpoint - so anything called directly here runs ON the event loop and
    # stalls every other request in the process for its duration. Measured
    # before this was fixed: three concurrent /jobs/recommended took 1.5s, 2.9s
    # and 4.4s (perfectly serialised, not overlapping) and an unrelated trivial
    # GET issued alongside one took 1.43s instead of its usual 0.3s. Hence
    # asyncio.to_thread around each of them.
    profile_data = await asyncio.to_thread(get_profile_data, user_id)
    if not profile_data:
        raise HTTPException(status_code=404, detail="Profile not found")

    preferred_roles = profile_data.get("preferred_job_roles", [])
    background_tasks.add_task(_background_ingest_for_roles, user_id, preferred_roles)

    if legacy:
        # Use the embedding cached at profile-intelligence time; only recompute
        # (expensive SentenceTransformer encode) for profiles created before caching existed.
        profile_embedding = await asyncio.to_thread(get_cached_profile_embedding, user_id)
        if not profile_embedding:
            profile_embedding = await asyncio.to_thread(generate_profile_embedding, profile_data)

        if not profile_embedding:
            logger.warning("Profile embedding unavailable for user %s, returning unranked active jobs", user_id)
            fallback_jobs = await asyncio.to_thread(get_jobs_by_filter, JobFilter(), limit=15)
            return {"success": True, "data": fallback_jobs}

        matched_jobs = await asyncio.to_thread(
            match_jobs, profile_embedding, match_threshold=MATCH_THRESHOLD, match_count=40
        )
        return {"success": True, "data": matched_jobs, "total": len(matched_jobs)}

    # rank_jobs needs the profile_version to key its cache, but retrieval does
    # not, so the two go out together instead of one after the other.
    scored_jobs, profile_version = await asyncio.gather(
        asyncio.to_thread(retrieve_candidates, user_id, profile_data),
        asyncio.to_thread(get_profile_version, user_id),
    )

    if scored_jobs is None:
        # Embedding generation failed. Unlike the legacy path, this never
        # backfills with unfiltered active jobs - that fallback is exactly the
        # contamination bug this rework removes. The frontend already treats
        # a missing/empty `data` as its existing empty state.
        logger.warning("Profile embedding unavailable for user %s", user_id)
        return {"success": False, "data": [], "total": 0, "error": "embedding_unavailable"}

    ranked_jobs = await rank_jobs(
        user_id, scored_jobs[:TOP_CANDIDATES], profile_data, background_tasks,
        profile_version=profile_version,
    )
    top_matches = select_top_matches(ranked_jobs, top_n=limit)

    entries = [ranked_job.model_dump() for ranked_job in top_matches]
    job_ids = [entry["job"]["id"] for entry in entries if entry.get("job", {}).get("id")]
    cached_scores = await asyncio.to_thread(get_ats_scores_for_jobs, user_id, job_ids)
    entries = build_job_ats_summaries(profile_data, entries, cached_scores=cached_scores)
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

    # The job query and the profile read share no inputs, so they go out
    # together rather than one after the other. Every one of these is a
    # round trip to a Supabase region that is not local (~0.2-0.7s each
    # measured), which is the bulk of this endpoint's latency - the SQL
    # itself runs in tens of milliseconds.
    with ThreadPoolExecutor(max_workers=2) as pool:
        # Score-then-truncate over a wider pool, so the returned list is
        # genuinely the best matches for the query rather than the most
        # recently posted.
        candidates_future = pool.submit(
            get_jobs_by_filter,
            JobFilter(title=query or None),
            limit=max(SEARCH_CANDIDATE_POOL, limit),
        )
        profile_future = pool.submit(get_profile_data, user_id)
        candidates = candidates_future.result()
        profile_data = profile_future.result()

    entries: list[dict] = [{"job": job} for job in candidates]

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
