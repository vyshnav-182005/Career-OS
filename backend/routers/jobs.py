from fastapi import APIRouter, Depends, Query, HTTPException
from typing import List, Optional
import logging

from backend.models.job import JobFilter, IngestionStatistics
from backend.services.job_ingestion import JobIngestionWorkflow
from backend.services.job_providers.mock_provider import MockJobProvider
from backend.services.job_providers.adzuna_provider import AdzunaProvider
from backend.services.job_providers.jooble_provider import JoobleProvider
from backend.db.supabase_client import get_jobs_by_filter, get_profile_data, match_jobs
from backend.services.embeddings import generate_profile_embedding

logger = logging.getLogger(__name__)

router = APIRouter(prefix='/jobs', tags=['Jobs'])

# In a real application, providers would be configured via a registry or dependency injection
CONFIGURED_PROVIDERS = [
    MockJobProvider(),
    JoobleProvider()
]


@router.post("/ingest", response_model=IngestionStatistics, summary="Trigger Job Ingestion Workflow")
def trigger_job_ingestion():
    """
    Manually triggers the ingestion workflow to fetch jobs from all configured providers,
    normalize, deduplicate, and upsert them into the database.
    """
    workflow = JobIngestionWorkflow(providers=CONFIGURED_PROVIDERS)
    stats = workflow.run()
    return stats

@router.get("/recommended", summary="Get Recommended Jobs based on User Profile")
def get_recommended_jobs(user_id: str):
    """
    Reads preferred roles from user profile.
    Checks if jobs exist for those roles in the DB.
    If not, fetches them from providers (Jooble), stores them, and returns them.
    """
    profile_data = get_profile_data(user_id)
    if not profile_data:
        raise HTTPException(status_code=404, detail="Profile not found")
        
    preferred_roles = profile_data.get("preferred_job_roles", [])
    
    for role_entry in preferred_roles:
        role_title = role_entry.get("title") if isinstance(role_entry, dict) else getattr(role_entry, "title", None)
        if not role_title: continue
        
        try:
            workflow = JobIngestionWorkflow(providers=[JoobleProvider()])
            workflow.run(query=role_title)
        except Exception as e:
            logger.warning("Ingestion failed for role '%s': %s", role_title, e)
            
    # Generate profile embedding
    profile_embedding = generate_profile_embedding(profile_data)
    
    if not profile_embedding:
        # Embedding generation failed (model download error, etc.)
        # Fall back to returning active jobs instead of crashing
        logger.warning("Profile embedding generation failed for user %s, returning unranked active jobs", user_id)
        fallback_jobs = get_jobs_by_filter(JobFilter())
        return {"success": True, "data": fallback_jobs[:15]}
    
    # Fetch top matches
    matched_jobs = match_jobs(profile_embedding, match_threshold=-1.0, match_count=15)
            
    return {"success": True, "data": matched_jobs}


@router.get("", summary="Get Active Jobs")
def get_jobs(
    title: Optional[str] = Query(None, description="Filter by job title"),
    company: Optional[str] = Query(None, description="Filter by company name"),
    location: Optional[str] = Query(None, description="Filter by location"),
    employment_type: Optional[str] = Query(None, description="Filter by employment type"),
    skills: Optional[List[str]] = Query(None, description="Filter by skills")
):
    """
    Retrieves active jobs, optionally filtering by various attributes.
    """
    filter_params = JobFilter(
        title=title,
        company=company,
        location=location,
        employment_type=employment_type,
        skills=skills
    )
    
    jobs = get_jobs_by_filter(filter_params)
    return {"success": True, "data": jobs}
