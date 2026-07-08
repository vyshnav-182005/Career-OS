"""
Supabase Client — persistence layer for profile intelligence data.

Upserts enriched profile data into the `profiles` table and uploads
resumes to the `resumes` storage bucket.
"""

import logging
import uuid
from typing import Optional

from supabase import create_client

from backend.config import settings
from backend.models.resume import ParsedResume
from backend.models.profile import ProfileIntelligence

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
    # At this point, we just save original_resume. 
    # ProfileIntelligence will be fully populated later.
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

