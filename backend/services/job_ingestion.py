import logging
from typing import List

from backend.models.job import NormalizedJob, IngestionStatistics, JobStatus
from backend.services.job_providers.base import BaseJobProvider
from backend.db.supabase_client import (
    upsert_jobs, 
    get_active_provider_job_ids, 
    delete_expired_jobs
)

logger = logging.getLogger(__name__)

class JobIngestionWorkflow:
    """
    Orchestrates fetching jobs from providers, normalizing, deduplicating,
    and upserting them into the database while tracking ingestion statistics.
    """
    
    def __init__(self, providers: List[BaseJobProvider]):
        self.providers = providers

    def run(self, query: str | None = None) -> IngestionStatistics:
        stats = IngestionStatistics()
        
        for provider in self.providers:
            logger.info("Starting ingestion for provider: %s", provider.provider_name)
            try:
                # 1. Fetch
                jobs = provider.fetch_jobs(query=query)
                stats.fetched += len(jobs)
                
                if not jobs:
                    continue

                # Get existing active job ids for this provider to track which ones expire
                existing_active_ids = set(get_active_provider_job_ids(provider.provider_name))
                
                jobs_to_upsert = []
                current_fetch_ids = set()

                # 2. Normalize and Prepare
                for job in jobs:
                    # In a real app we might do more rigorous validation here
                    # Pydantic has already validated the NormalizedJob object
                    current_fetch_ids.add(job.provider_job_id)
                    
                    # Basic logic for stats: 
                    # If it was already active, it's an update, otherwise it's an insert.
                    if job.provider_job_id in existing_active_ids:
                        stats.updated += 1
                    else:
                        stats.inserted += 1
                        # Generate embedding only for new jobs (to save computation)
                        # If we wanted to check for changes, we'd compare with the existing DB record.
                        try:
                            from backend.services.embeddings import generate_job_embedding
                            job.embedding = generate_job_embedding(job.title, job.description, job.skills)
                        except Exception as e:
                            logger.error("Failed to generate embedding for job %s: %s", job.provider_job_id, e)
                    
                    job_dict = job.model_dump()
                    job_dict["status"] = JobStatus.ACTIVE.value
                    
                    # Remove embedding if it's None or empty to avoid
                    # 'vector must have at least 1 dimension' DB errors
                    if not job_dict.get("embedding"):
                        job_dict.pop("embedding", None)

                    # raw_payload is for debugging only, not a DB column
                    job_dict.pop("raw_payload", None)

                    # Convert datetime to isoformat string if necessary, 
                    if job_dict.get("posted_date"):
                        job_dict["posted_date"] = job_dict["posted_date"].isoformat()
                        
                    jobs_to_upsert.append(job_dict)

                # 3. Upsert
                upsert_jobs(jobs_to_upsert)

                # 4. Handle Expirations
                # Jobs that were active but are not in the current fetch are considered expired.
                # Only expire if it's not a targeted fetch (i.e. no query was provided)
                if not query:
                    expired_ids = existing_active_ids - current_fetch_ids
                    if expired_ids:
                        delete_expired_jobs(provider.provider_name, list(expired_ids))
                        stats.expired += len(expired_ids)
                    
            except Exception as e:
                logger.exception("Error during ingestion for provider %s: %s", provider.provider_name, e)
                stats.failed += 1

        logger.info("Ingestion workflow completed. Stats: %s", stats.model_dump())
        return stats
