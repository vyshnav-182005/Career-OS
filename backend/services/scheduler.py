import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from backend.services import taxonomy
from backend.services.job_ingestion import JobIngestionWorkflow
from backend.services.job_providers.registry import build_providers
from backend.db.supabase_client import get_all_preferred_role_titles

logger = logging.getLogger(__name__)

# Singleton scheduler
scheduler = AsyncIOScheduler()

def _ingestion_queries() -> list[str]:
    """
    What the scheduled run fetches: the roles real profiles asked for, plus a
    standing seed query per role family.

    The seeds matter for coverage the demand-driven half cannot give. Fetching
    only what current users want means a domain nobody has signed up for stays
    empty, so the first candidate from it lands on a page with nothing on it -
    and the background fetch that would populate it runs after their response
    has already been sent. Seeding every family keeps a floor of inventory for
    the branches of engineering that have no users yet.

    Profile-derived titles come first so a real user's exact role is fetched
    before the generic seeds if a run is cut short.
    """
    role_titles = get_all_preferred_role_titles() or []
    seen = {title.lower() for title in role_titles}
    queries = list(role_titles)
    for seed in taxonomy.all_seed_queries():
        if seed.lower() not in seen:
            seen.add(seed.lower())
            queries.append(seed)
    return queries


def run_job_ingestion():
    """Wrapper to run the ingestion workflow, targeted at the distinct
    preferred job roles across all profiles plus the per-family seed queries.
    An unqualified fetch pulls Jooble's generic high-volume firehose, which
    pollutes the pool for everyone, so we never fall back to one."""
    logger.info("Starting scheduled job ingestion...")

    role_titles = _ingestion_queries()
    if not role_titles:
        logger.info("No ingestion queries resolved; skipping scheduled ingestion.")
        return

    logger.info("Scheduled ingestion will run %d queries.", len(role_titles))
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
