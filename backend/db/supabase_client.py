import logging
import uuid
from typing import Optional, List, Dict, Any

from supabase import create_client

from backend.config import settings
from backend.models.resume import ParsedResume
from backend.models.profile import ProfileIntelligence
from backend.models.job import JobFilter

logger = logging.getLogger(__name__)


def get_supabase_client():
    return create_client(
        supabase_url=settings.supabase_url,
        supabase_key=settings.supabase_service_key,
    )


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
    initial_profile_data = {
        "original_resume": parsed_resume.model_dump(),
        "preferred_job_roles": [],
        "strengths": []
    }

    row = {
        "user_id": user_id,
        "profile_data": initial_profile_data,
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


def update_profile_intelligence(user_id: str, profile_intelligence: ProfileIntelligence) -> None:
    client = get_supabase_client()
    try:
        row = {
            "user_id": user_id,
            "profile_data": profile_intelligence.model_dump(),
        }
        client.table("profiles").upsert(row, on_conflict="user_id").execute()
        logger.info("Enriched profile updated successfully for user_id=%s", user_id)
    except Exception:
        logger.exception("Failed to update profile intelligence for user_id=%s", user_id)
        raise


# --- Jobs DB Operations ---

def get_active_provider_job_ids(provider: str) -> List[str]:
    """
    Returns a list of provider_job_ids for jobs that are currently active for a given provider.
    """
    client = get_supabase_client()
    try:
        result = (
            client.table("jobs")
            .select("provider_job_id")
            .eq("provider", provider)
            .eq("status", "ACTIVE")
            .execute()
        )
        return [row["provider_job_id"] for row in result.data]
    except Exception:
        logger.exception("Failed to fetch active provider job ids for %s", provider)
        return []

def upsert_jobs(jobs_data: List[Dict[str, Any]]) -> None:
    """
    Upserts a batch of jobs into the jobs table.
    """
    if not jobs_data:
        return
    client = get_supabase_client()
    try:
        client.table("jobs").upsert(
            jobs_data, 
            on_conflict="provider,provider_job_id"
        ).execute()
        logger.info("Successfully upserted %d jobs.", len(jobs_data))
    except Exception:
        logger.exception("Failed to upsert jobs.")
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

def get_jobs_by_filter(filter_params: JobFilter) -> List[Dict[str, Any]]:
    """
    Retrieves active jobs based on filters using PostgreSQL functionality.
    """
    client = get_supabase_client()
    query = client.table("jobs").select("*").eq("status", "ACTIVE")
    
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

    try:
        result = query.execute()
        return result.data
    except Exception:
        logger.exception("Failed to fetch jobs by filter.")
        return []

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
        logger.exception("Failed to match jobs by profile embedding.")
        return []
