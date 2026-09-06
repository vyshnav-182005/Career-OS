import hashlib
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any

from supabase import create_client

from backend.config import settings
from backend.models.resume import ParsedResume
from backend.models.profile import ProfileIntelligence
from backend.models.job import JobFilter
from backend.services.profile_sections import merge_reparsed_sections

logger = logging.getLogger(__name__)


def get_supabase_client():
    return create_client(
        supabase_url=settings.supabase_url,
        supabase_key=settings.supabase_service_key,
    )


def _compute_profile_version(profile_data: dict) -> str:
    """
    sha256 of profile_data, used as the job_matches cache key so a cached
    LLM verdict is invalidated the moment the underlying profile changes.
    """
    payload = json.dumps(profile_data, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def upsert_parsed_resume(
    user_id: str,
    parsed_resume: ParsedResume,
    file_bytes: bytes,
    content_type: str,
    source_filename: str,
) -> None:
    """
    Uploads the resume to Supabase Storage and upserts the initial parsed profile data.
    """
    client = get_supabase_client()
    
    # 1. Upload file to Storage
    ext = ".pdf" if content_type == "application/pdf" else ".docx"
    storage_path = f"{user_id}/{uuid.uuid4()}{ext}"
    
    logger.info("Uploading resume to storage bucket 'resumes' at path: %s", storage_path)
    try:
        client.storage.from_("resumes").upload(
            path=storage_path,
            file=file_bytes,
            file_options={"content-type": content_type}
        )
        resume_url = client.storage.from_("resumes").get_public_url(storage_path)
        logger.info("Resume uploaded successfully: %s", resume_url)
    except Exception as e:
        logger.exception("Failed to upload resume to storage")
        raise e

    # 2. Upsert Initial Profile Data
    #
    # A re-parse replaces what the resume states, but not what the profile has
    # that no resume ever will. Certifications and publications are editable in
    # the profile editor, so replacing those arrays wholesale is what used to
    # delete a hand-added certification the moment an older resume was
    # uploaded. The GitHub state is carried over for the same reason: it
    # describes the linked account, not this file, and rebuilding its README
    # cache costs a fetch and a completion per repo.
    existing = get_profile_data(user_id) or {}
    existing_resume = existing.get("original_resume") or {}

    initial_profile_data = {
        "original_resume": merge_reparsed_sections(existing_resume, parsed_resume.model_dump()),
        # Both are re-derived by the profile intelligence workflow that runs
        # straight after this, so they are deliberately not carried over.
        "preferred_job_roles": [],
        "strengths": []
    }
    for carried in ("github_summary", "github_sync"):
        if existing.get(carried) is not None:
            initial_profile_data[carried] = existing[carried]

    row = {
        "user_id": user_id,
        "profile_data": initial_profile_data,
        "profile_version": _compute_profile_version(initial_profile_data),
        "source_filename": source_filename,
        "resume_url": resume_url,
    }

    logger.info("Upserting initial profile for user_id=%s", user_id)

    try:
        result = (
            client.table("profiles")
            .upsert(row, on_conflict="user_id")
            .execute()
        )
        logger.info("Initial profile upserted successfully for user_id=%s", user_id)
    except Exception:
        logger.exception("Failed to upsert profile for user_id=%s", user_id)
        raise


def save_profile_data(user_id: str, profile_data: dict, bump_version: bool = True) -> bool:
    """Persists profile_data, re-keying the job-match cache when it changed.

    job_matches is cached against profile_version, so a changed profile has to
    drop stale LLM verdicts with it. Bookkeeping writes that changed no profile
    text pass bump_version=False rather than throwing that cache away.
    """
    row: dict = {"profile_data": profile_data}
    if bump_version:
        row["profile_version"] = _compute_profile_version(profile_data)

    client = get_supabase_client()
    try:
        client.table("profiles").update(row).eq("user_id", user_id).execute()
        return True
    except Exception:
        logger.exception("Failed to save profile_data for user_id=%s", user_id)
        return False


def get_profile_data(user_id: str) -> Optional[dict]:
    client = get_supabase_client()
    try:
        result = client.table("profiles").select("profile_data").eq("user_id", user_id).execute()
        if result.data:
            return result.data[0].get("profile_data")
        return None
    except Exception:
        logger.exception("Failed to get profile for user_id=%s", user_id)
        return None


def get_all_preferred_role_titles() -> List[str]:
    """
    Returns the distinct preferred_job_roles[].title values across every
    profile, for role-targeted scheduled ingestion.
    """
    client = get_supabase_client()
    try:
        result = client.table("profiles").select("profile_data").execute()
        titles: List[str] = []
        seen = set()
        for row in result.data or []:
            roles = (row.get("profile_data") or {}).get("preferred_job_roles") or []
            for role in roles:
                title = role.get("title") if isinstance(role, dict) else None
                if title and title not in seen:
                    seen.add(title)
                    titles.append(title)
        return titles
    except Exception:
        logger.exception("Failed to get preferred role titles across profiles")
        return []


def update_profile_intelligence(
    user_id: str,
    profile_intelligence: ProfileIntelligence,
    profile_embedding: Optional[List[float]] = None,
) -> None:
    client = get_supabase_client()
    try:
        profile_data = profile_intelligence.model_dump()
        row = {
            "user_id": user_id,
            "profile_data": profile_data,
            "profile_version": _compute_profile_version(profile_data),
        }
        if profile_embedding:
            row["profile_embedding"] = profile_embedding
        client.table("profiles").upsert(row, on_conflict="user_id").execute()
        logger.info("Enriched profile updated successfully for user_id=%s", user_id)
    except Exception:
        logger.exception("Failed to update profile intelligence for user_id=%s", user_id)
        raise


def get_cached_profile_embedding(user_id: str) -> Optional[List[float]]:
    """
    Returns the profile embedding cached at profile-intelligence time, if any,
    so callers don't need to recompute it (SentenceTransformer encode) on every request.
    """
    client = get_supabase_client()
    try:
        result = (
            client.table("profiles")
            .select("profile_embedding")
            .eq("user_id", user_id)
            .execute()
        )
        if result.data:
            return result.data[0].get("profile_embedding")
        return None
    except Exception:
        logger.exception("Failed to get cached profile embedding for user_id=%s", user_id)
        return None


# --- Jobs DB Operations ---

def get_active_provider_job_hashes(provider: str) -> Dict[str, str]:
    """
    Returns {provider_job_id: content_hash} for jobs currently active for a
    given provider. Used both to distinguish inserts from updates and to skip
    re-embedding a job whose content_hash hasn't changed since last ingest.
    """
    client = get_supabase_client()
    try:
        result = (
            client.table("jobs")
            .select("provider_job_id, content_hash")
            .eq("provider", provider)
            .eq("status", "ACTIVE")
            .execute()
        )
        return {row["provider_job_id"]: row.get("content_hash") for row in result.data}
    except Exception:
        logger.exception("Failed to fetch active provider job hashes for %s", provider)
        return {}

# A provider's fetch can run to several hundred rows once fanned out across
# every seeded ATS company (a big employer alone can have 100+ open roles),
# each carrying a full description plus an embedding vector. Sending all of
# it as one upsert risks Postgres's statement_timeout on a large enough run -
# this is what was canceling ingestion outright. Chunking costs nothing when
# a provider's batch is already small, and means one oversized run degrades
# to "slower, in pieces" instead of failing completely.
JOBS_UPSERT_BATCH_SIZE = 200


def upsert_jobs(jobs_data: List[Dict[str, Any]]) -> None:
    """
    Upserts jobs into the jobs table in chunks of JOBS_UPSERT_BATCH_SIZE, so a
    provider's full fetch never lands in one statement large enough to hit
    Postgres's statement timeout. Each chunk is its own request; a batch that
    fails still raises (matching the previous single-call behavior for
    callers), but whatever batches already committed stay committed rather
    than the whole run being lost to one oversized statement.
    """
    if not jobs_data:
        return
    client = get_supabase_client()
    total = len(jobs_data)
    for start in range(0, total, JOBS_UPSERT_BATCH_SIZE):
        chunk = jobs_data[start:start + JOBS_UPSERT_BATCH_SIZE]
        try:
            client.table("jobs").upsert(
                chunk,
                on_conflict="provider,provider_job_id"
            ).execute()
            logger.info(
                "Successfully upserted %d jobs (batch %d-%d of %d).",
                len(chunk), start + 1, start + len(chunk), total,
            )
        except Exception:
            logger.exception(
                "Failed to upsert jobs batch %d-%d of %d.", start + 1, start + len(chunk), total
            )
            raise

def delete_expired_jobs(provider: str, provider_job_ids: List[str]) -> None:
    """
    Deletes jobs that are expired for the given provider and provider_job_ids.
    """
    if not provider_job_ids:
        return
    client = get_supabase_client()
    try:
        client.table("jobs").delete().eq("provider", provider).in_("provider_job_id", provider_job_ids).execute()
        logger.info("Deleted %d expired jobs for provider %s.", len(provider_job_ids), provider)
    except Exception:
        logger.exception("Failed to delete expired jobs for provider %s.", provider)
        raise

# Columns needed for job list/detail views. Excludes `embedding` (384-dim vector,
# never used by the frontend) and `raw_payload` (provider debug blob) to keep list
# responses small.
JOB_LIST_COLUMNS = (
    "id, provider, provider_job_id, title, company, location, description, skills, "
    "employment_type, salary, posted_date, url, status, created_at, updated_at"
)


def get_jobs_by_filter(
    filter_params: JobFilter, limit: int = 20, offset: int = 0
) -> List[Dict[str, Any]]:
    """
    Retrieves active jobs based on filters using PostgreSQL functionality.
    """
    client = get_supabase_client()
    query = client.table("jobs").select(JOB_LIST_COLUMNS).eq("status", "ACTIVE")

    if filter_params.title:
        query = query.ilike("title", f"%{filter_params.title}%")
    if filter_params.company:
        query = query.ilike("company", f"%{filter_params.company}%")
    if filter_params.location:
        query = query.ilike("location", f"%{filter_params.location}%")
    if filter_params.employment_type:
        query = query.eq("employment_type", filter_params.employment_type)
    if filter_params.skills:
        # Check if skills array contains the requested skills
        query = query.contains("skills", filter_params.skills)

    query = query.order("posted_date", desc=True).range(offset, offset + limit - 1)

    try:
        result = query.execute()
        return result.data
    except Exception:
        logger.exception("Failed to fetch jobs by filter.")
        return []


def get_job_by_id(job_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieves a single job by its primary key, including its full description —
    used by the resume optimization flow to pull the JD server-side rather than
    trusting client-supplied text.
    """
    client = get_supabase_client()
    try:
        result = (
            client.table("jobs")
            .select(JOB_LIST_COLUMNS)
            .eq("id", job_id)
            .limit(1)
            .execute()
        )
        if result.data:
            return result.data[0]
        return None
    except Exception:
        logger.exception("Failed to fetch job by id=%s", job_id)
        return None

def match_jobs(profile_embedding: List[float], match_threshold: float = 0.0, match_count: int = 15) -> List[Dict[str, Any]]:
    """
    Calls the match_jobs RPC to get recommended jobs based on profile embedding.
    """
    if not profile_embedding:
        return []

    client = get_supabase_client()
    try:
        response = client.rpc(
            "match_jobs",
            {
                "query_embedding": profile_embedding,
                "match_threshold": match_threshold,
                "match_count": match_count
            }
        ).execute()
        return response.data
    except Exception:
        logger.exception("Failed to match jobs by profile embedding, falling back.")
        return []


def match_jobs_v2(
    profile_embedding: List[float],
    target_families: Optional[List[str]] = None,
    excluded_families: Optional[List[str]] = None,
    must_have_skills: Optional[List[str]] = None,
    min_posted_date: Optional[str] = None,
    locations: Optional[List[str]] = None,
    match_threshold: float = 0.0,
    match_count: int = 60,
) -> List[Dict[str, Any]]:
    """
    Calls the match_jobs_v2 RPC: vector similarity ranking plus hard SQL
    predicates on role_family/excluded_families/posted_date/location, unlike
    match_jobs (v1) which only ranks and never gates.
    """
    if not profile_embedding:
        return []
    client = get_supabase_client()
    try:
        response = client.rpc(
            "match_jobs_v2",
            {
                "query_embedding": profile_embedding,
                "target_families": target_families or [],
                "excluded_families": excluded_families or [],
                "must_have_skills": must_have_skills or [],
                "min_posted_date": min_posted_date,
                "locations": locations or [],
                "match_threshold": match_threshold,
                "match_count": match_count,
            },
        ).execute()
        return response.data
    except Exception:
        logger.exception("Failed to match jobs via match_jobs_v2.")
        return []


def search_jobs_fulltext(
    search_query: str, target_families: Optional[List[str]] = None, match_count: int = 60
) -> List[Dict[str, Any]]:
    """Calls the search_jobs_fulltext RPC - the lexical leg of hybrid retrieval."""
    if not search_query:
        return []
    client = get_supabase_client()
    try:
        response = client.rpc(
            "search_jobs_fulltext",
            {
                "search_query": search_query,
                "target_families": target_families or [],
                "match_count": match_count,
            },
        ).execute()
        return response.data
    except Exception:
        logger.exception("Failed to search jobs via search_jobs_fulltext.")
        return []


def get_jobs_by_role_family(role_families: List[str], match_count: int = 60) -> List[Dict[str, Any]]:
    """
    Direct role_family match ordered by freshness - the third hybrid-retrieval
    leg. Covers cold-start/bad-embedding cases since it needs no vector at all.
    """
    if not role_families:
        return []
    client = get_supabase_client()
    try:
        result = (
            client.table("jobs")
            .select(JOB_LIST_COLUMNS + ", role_family")
            .eq("status", "ACTIVE")
            .in_("role_family", role_families)
            .order("posted_date", desc=True)
            .limit(match_count)
            .execute()
        )
        return result.data
    except Exception:
        logger.exception("Failed to fetch jobs by role_family.")
        return []


# --- Job Fit Analysis (project bullets + ATS score) DB Operations ---

def get_job_fit_analysis(user_id: str, job_id: str) -> Optional[Dict[str, Any]]:
    """Returns the cached job-fit row (optimized resume snapshot / projects / ATS score) for a (user, job) pair, if any."""
    client = get_supabase_client()
    try:
        result = (
            client.table("job_resume_optimizations")
            .select("optimized_resume_json, optimized_projects, ats_score, profile_version, updated_at")
            .eq("user_id", user_id)
            .eq("job_id", job_id)
            .execute()
        )
        if result.data:
            return result.data[0]
        return None
    except Exception:
        logger.exception("Failed to get job fit analysis for user_id=%s job_id=%s", user_id, job_id)
        return None


def get_ats_scores_for_jobs(user_id: str, job_ids: List[str]) -> Dict[str, Dict[str, Any]]:
    """
    Bulk-fetches previously computed ATS scores for a set of jobs, keyed by
    job_id. Used by the job list so an already-analyzed job shows its real
    score on the card instead of the deterministic estimate. One query for the
    whole page - never one per card.

    Failures return {} rather than raising: a missing cache only means the list
    falls back to estimated scores.
    """
    if not job_ids:
        return {}
    client = get_supabase_client()
    try:
        result = (
            client.table("job_resume_optimizations")
            .select("job_id, ats_score")
            .eq("user_id", user_id)
            .in_("job_id", job_ids)
            .execute()
        )
        return {
            row["job_id"]: row["ats_score"]
            for row in (result.data or [])
            if row.get("job_id") and isinstance(row.get("ats_score"), dict)
        }
    except Exception:
        logger.exception("Failed to bulk-fetch ATS scores for user_id=%s", user_id)
        return {}


def upsert_optimized_resume_snapshot(
    user_id: str,
    job_id: str,
    optimized_resume_json: Dict[str, Any],
    optimized_projects: List[Dict[str, Any]],
    profile_version: Optional[str] = None,
) -> None:
    """
    Persists the tailored resume + derived project bullets for a (user, job) pair,
    tagged with the profile_version it was generated from so a later call can
    tell whether the profile's content has actually changed since (see
    get_profile_version) rather than relying on the row's updated_at timestamp,
    which is bumped by any write at all.
    """
    client = get_supabase_client()
    try:
        row = {
            "user_id": user_id,
            "job_id": job_id,
            "optimized_resume_json": optimized_resume_json,
            "optimized_projects": optimized_projects,
            "profile_version": profile_version,
        }
        client.table("job_resume_optimizations").upsert(row, on_conflict="user_id,job_id").execute()
    except Exception:
        logger.exception("Failed to upsert optimized resume snapshot for user_id=%s job_id=%s", user_id, job_id)
        raise


def upsert_ats_score(user_id: str, job_id: str, ats_score: Dict[str, Any]) -> None:
    """Persists the ATS score for a (user, job) pair without touching the resume snapshot columns."""
    client = get_supabase_client()
    try:
        row = {
            "user_id": user_id,
            "job_id": job_id,
            "ats_score": ats_score,
        }
        client.table("job_resume_optimizations").upsert(row, on_conflict="user_id,job_id").execute()
    except Exception:
        logger.exception("Failed to upsert ATS score for user_id=%s job_id=%s", user_id, job_id)
        return []


# --- Job Matching Agent (Phase 3) DB Operations ---

def get_profile_version(user_id: str) -> Optional[str]:
    """Returns the profile's current version hash - the job_matches cache key."""
    client = get_supabase_client()
    try:
        result = client.table("profiles").select("profile_version").eq("user_id", user_id).execute()
        if result.data:
            return result.data[0].get("profile_version")
        return None
    except Exception:
        logger.exception("Failed to get profile_version for user_id=%s", user_id)
        return None


# How long a feature-ranking fallback row stays servable. Real LLM verdicts are
# cached until the profile changes; a fallback is the record of work that did
# not happen, so it gets a short life instead - long enough that paging around
# the Jobs page doesn't re-fire the whole LLM fan-out over a provider's bad
# minute, short enough that the results heal on their own without waiting for
# the user to edit their profile. See database/job_matches_from_llm_migration.sql.
FALLBACK_CACHE_TTL_SECONDS = 600


def get_cached_job_matches(
    user_id: str, job_ids: List[str], profile_version: Optional[str]
) -> Dict[str, Dict[str, Any]]:
    """
    Returns cached job_matches rows keyed by job_id, scoped to the current
    profile_version - a stale-version row (profile changed since) is never
    returned, forcing a fresh LLM call instead of serving an outdated verdict.

    Fallback rows (from_llm = false) additionally expire after
    FALLBACK_CACHE_TTL_SECONDS, so a transient LLM outage is absorbed for a few
    minutes rather than either re-fired on every single request or pinned to
    the job until the profile changes.
    """
    if not job_ids or not profile_version:
        return {}
    client = get_supabase_client()

    def _select(columns: str):
        return (
            client.table("job_matches")
            .select(columns)
            .eq("user_id", user_id)
            .eq("profile_version", profile_version)
            .in_("job_id", job_ids)
            .execute()
        )

    base_columns = "job_id, verdict, score, reason, matched_skills, missing_skills"
    try:
        result = _select(f"{base_columns}, from_llm, updated_at")
    except Exception:
        # Most likely the from_llm migration has not been applied here. Falling
        # back to the columns that certainly exist keeps the cache working
        # (every stored row then reads as a real verdict, which is what they all
        # were before the column existed). Returning {} instead would silently
        # disable the cache and put the full LLM fan-out back on every request -
        # a large, hard-to-attribute slowdown from a missing migration.
        logger.warning(
            "job_matches select with from_llm failed for user_id=%s; retrying without it. "
            "Apply database/job_matches_from_llm_migration.sql.",
            user_id,
            exc_info=True,
        )
        try:
            result = _select(base_columns)
        except Exception:
            logger.exception("Failed to get cached job matches for user_id=%s", user_id)
            return {}

    cutoff = datetime.now(timezone.utc) - timedelta(seconds=FALLBACK_CACHE_TTL_SECONDS)
    fresh: Dict[str, Dict[str, Any]] = {}
    for row in result.data:
        # Absent column (migration not yet applied) reads as a real verdict,
        # which is what every row written before from_llm existed actually was.
        if row.get("from_llm", True) or _parsed_timestamp(row.get("updated_at")) > cutoff:
            fresh[row["job_id"]] = row
    return fresh


def _parsed_timestamp(value: Any) -> datetime:
    """
    Parses a PostgREST timestamptz. Returns the epoch on anything unparseable,
    so a malformed value ages a fallback row out rather than keeping it alive.
    """
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            pass
    return datetime.min.replace(tzinfo=timezone.utc)


def upsert_job_matches(rows: List[Dict[str, Any]]) -> None:
    """Persists a batch of Job Matching Agent results, one row per (user, job)."""
    if not rows:
        return
    client = get_supabase_client()
    try:
        client.table("job_matches").upsert(rows, on_conflict="user_id,job_id").execute()
        return
    except Exception:
        # Mirrors the read side: if the from_llm migration hasn't been applied,
        # write the rest of the row rather than losing the verdict entirely.
        # Only real verdicts are kept here - without the column there is no way
        # to age a fallback out, and an immortal "AI reviewer was unavailable"
        # is worse than re-running the call.
        if not any("from_llm" in row for row in rows):
            logger.exception("Failed to upsert job_matches (%d rows)", len(rows))
            return
        logger.warning(
            "job_matches upsert with from_llm failed; retrying without it. "
            "Apply database/job_matches_from_llm_migration.sql.",
            exc_info=True,
        )

    legacy_rows = [
        {k: v for k, v in row.items() if k != "from_llm"}
        for row in rows
        if row.get("from_llm", True)
    ]
    if not legacy_rows:
        return
    try:
        client.table("job_matches").upsert(legacy_rows, on_conflict="user_id,job_id").execute()
    except Exception:
        logger.exception("Failed to upsert job_matches (%d rows)", len(legacy_rows))


# --- Job feedback (Phase 4) DB Operations ---

def upsert_job_feedback(user_id: str, job_id: str, vote: str) -> bool:
    """Records a thumbs up/down vote on a recommended job, one row per (user, job).
    Re-voting overwrites the previous vote rather than accumulating rows."""
    client = get_supabase_client()
    try:
        client.table("job_feedback").upsert(
            {"user_id": user_id, "job_id": job_id, "vote": vote},
            on_conflict="user_id,job_id",
        ).execute()
        return True
    except Exception:
        logger.exception("Failed to upsert job_feedback for user_id=%s job_id=%s", user_id, job_id)
        return False
