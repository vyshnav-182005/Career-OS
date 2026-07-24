import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from backend.services.job_ingestion import JobIngestionWorkflow
from backend.services.job_providers.adzuna_provider import AdzunaProvider
from backend.services.job_providers.jooble_provider import JoobleProvider

logger = logging.getLogger(__name__)

# Singleton scheduler
scheduler = AsyncIOScheduler()

def run_job_ingestion():
    """Wrapper to run the ingestion workflow."""
    logger.info("Starting scheduled job ingestion...")
    providers = [JoobleProvider()]
    workflow = JobIngestionWorkflow(providers=providers)
    
    try:
        # Ingestion workflow is synchronous, we run it directly. 
        # (APScheduler supports running sync functions in its thread pool)
        stats = workflow.run()
        logger.info(f"Scheduled job ingestion completed: {stats.model_dump()}")
    except Exception as e:
        logger.exception("Scheduled job ingestion failed.")

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
