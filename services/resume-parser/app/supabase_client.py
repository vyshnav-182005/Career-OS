"""
Supabase Client — persistence layer for profile intelligence data.

Upserts enriched profile data into the `profiles` table so it serves
as the canonical data source for all downstream services and AI agents.
"""

import logging

from supabase import create_client

from app.config import get_settings
from app.profile_models import ProfileIntelligence

logger = logging.getLogger(__name__)


def upsert_profile(
    user_id: str,
    profile_intelligence: ProfileIntelligence,
    source_filename: str | None = None,
) -> None:
    """
    Upsert a user's enriched profile into the Supabase `profiles` table.

    Args:
        user_id: The authenticated user's ID (matches auth.users.id).
        profile_intelligence: The full ProfileIntelligence model to persist.
        source_filename: Optional original filename of the uploaded resume.

    The profile_data column stores the complete ProfileIntelligence as JSONB.
    Uses upsert with on_conflict='user_id' so re-uploads update the existing row.
    """
    settings = get_settings()

    client = create_client(
        supabase_url=settings.supabase_url,
        supabase_key=settings.supabase_service_key,
    )

    row = {
        "user_id": user_id,
        "profile_data": profile_intelligence.model_dump(),
        "source_filename": source_filename,
    }

    logger.info("Upserting profile for user_id=%s (file=%s)", user_id, source_filename)

    try:
        result = (
            client.table("profiles")
            .upsert(row, on_conflict="user_id")
            .execute()
        )
        logger.info(
            "Profile upserted successfully for user_id=%s — %d row(s) affected",
            user_id,
            len(result.data) if result.data else 0,
        )
    except Exception:
        logger.exception("Failed to upsert profile for user_id=%s", user_id)
        raise
