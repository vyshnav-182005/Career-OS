import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from backend.services.job_ingestion import JobIngestionWorkflow
from backend.services.job_providers.registry import build_providers
from backend.db.supabase_client import get_all_preferred_role_titles

logger = logging.getLogger(__name__)

# Singleton scheduler
scheduler = AsyncIOScheduler()

def run_job_ingestion():
    """Wrapper to run the ingestion workflow, targeted at the distinct
    preferred job roles across all profiles. An unqualified fetch pulls
    Jooble's generic high-volume firehose, which pollutes the pool for
    everyone, so we never fall back to one."""
    logger.info("Starting scheduled job ingestion...")

    role_titles = get_all_preferred_role_titles()
    if not role_titles:
        logger.info("No preferred job roles found across profiles; skipping scheduled ingestion.")
        return

    workflow = JobIngestionWorkflow(providers=build_providers())
    for role_title in role_titles:
        try:
            # Ingestion workflow is synchronous, we run it directly.
            # (APScheduler supports running sync functions in its thread pool)
            stats = workflow.run(query=role_title)
            logger.info(f"Scheduled job ingestion for role '{role_title}' completed: {stats.model_dump()}")
        except Exception as e:
            logger.exception("Scheduled job ingestion failed for role '%s'.", role_title)

def start_scheduler():
    if not scheduler.running:
        # Schedule the job every 6 hours
        scheduler.add_job(
            run_job_ingestion,
            trigger=IntervalTrigger(hours=6),
            id='job_ingestion_sync',
            name='Sync job postings every 6 hours',
            replace_existing=True
        )
        scheduler.start()
        logger.info("Scheduler started.")

def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown()
        logger.info("Scheduler stopped.")
