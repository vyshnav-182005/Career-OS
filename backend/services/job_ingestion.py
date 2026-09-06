import hashlib
import logging
from datetime import datetime, timezone
from typing import List

from backend.models.job import NormalizedJob, IngestionStatistics, JobStatus
from backend.services.job_providers.base import BaseJobProvider
from backend.services.embeddings import generate_job_embeddings
from backend.services import taxonomy
from backend.db.supabase_client import (
    upsert_jobs,
    get_active_provider_job_hashes,
    delete_expired_jobs
)

logger = logging.getLogger(__name__)


def compute_content_hash(title: str, company: str, description: str | None, skills: List[str]) -> str:
    """
    Fingerprints a job's user-visible content so ingestion can tell an
    unchanged repost apart from a genuinely updated listing, and skip
    re-embedding the former.
    """
    payload = "|".join([title or "", company or "", description or "", ",".join(sorted(skills or []))])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


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

                # Get existing active jobs' content hashes for this provider, to
                # track which ones expire and which are unchanged reposts.
                existing_hashes = get_active_provider_job_hashes(provider.provider_name)
                existing_active_ids = set(existing_hashes.keys())

                jobs_to_upsert = []
                current_fetch_ids = set()

                # 2. Normalize and Prepare
                #
                # Two passes rather than one: the first decides which jobs need
                # a (re)embed, then they are encoded in one batched call, and
                # the second builds the payloads. The transformer is far faster
                # over a list than over the same texts one at a time, and this
                # runs as a background task while the user's next search is
                # competing for the same cores.
                unchanged_ids: set[str] = set()
                needs_embedding: list[NormalizedJob] = []

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

                    job.role_family = taxonomy.classify_title(job.title)
                    job.source_query = query
                    job.last_seen_at = datetime.now(timezone.utc)
                    job.content_hash = compute_content_hash(job.title, job.company, job.description, job.skills)

                    if (
                        job.provider_job_id in existing_hashes
                        and existing_hashes[job.provider_job_id] == job.content_hash
                    ):
                        # Nothing about the job changed since it was last embedded —
                        # skip the (expensive) re-embed and leave the stored vector
                        # untouched by omitting it from the upsert payload below.
                        job.embedding = None
                        unchanged_ids.add(job.provider_job_id)
                    else:
                        # (Re)generate the embedding for new or changed jobs, so a job
                        # that was ingested before embeddings existed (or with a stale
                        # one) doesn't keep a missing/outdated vector forever.
                        needs_embedding.append(job)

                if needs_embedding:
                    try:
                        embeddings = generate_job_embeddings(
                            [(job.title, job.description, job.skills) for job in needs_embedding]
                        )
                    except Exception as e:
                        # generate_job_embeddings contains its own failures and
                        # returns None entries, so this is belt-and-braces: a
                        # surprise here must cost this provider's embeddings,
                        # not abort the whole run before the upsert.
                        logger.error("Failed to generate embeddings for %d jobs: %s", len(needs_embedding), e)
                        embeddings = [None] * len(needs_embedding)
                    for job, embedding in zip(needs_embedding, embeddings):
                        job.embedding = embedding

                for job in jobs:
                    content_unchanged = job.provider_job_id in unchanged_ids

                    if not content_unchanged and not job.embedding:
                        # An unembedded job is invisible to vector matching forever,
                        # so skip persisting it rather than storing it unranked.
                        stats.skipped += 1
                        continue

                    job_dict = job.model_dump()
                    job_dict["status"] = JobStatus.ACTIVE.value

                    # raw_payload is for debugging only, not a DB column
                    job_dict.pop("raw_payload", None)

                    if content_unchanged:
                        # Omitting the key (rather than sending None) leaves the
                        # existing embedding column untouched on upsert.
                        job_dict.pop("embedding", None)

                    # Convert datetime to isoformat string if necessary,
                    if job_dict.get("posted_date"):
                        job_dict["posted_date"] = job_dict["posted_date"].isoformat()
                    if job_dict.get("last_seen_at"):
                        job_dict["last_seen_at"] = job_dict["last_seen_at"].isoformat()

                    jobs_to_upsert.append(job_dict)

                # 3. Upsert
                upsert_jobs(jobs_to_upsert)

                # 4. Handle Expirations
                # Jobs that were active but are not in the current fetch are considered expired.
                # Only expire if it's not a targeted fetch (i.e. no query was provided)
                #
                # `fetch_complete` guards the other half of that assumption. A
                # fan-out provider (the ATS boards) can return a partial
                # inventory when one company's board times out - treating that
                # as "these jobs are gone" would delete every live job from
                # that company. A provider that only partially succeeded says
                # so, and we leave the existing rows alone until a clean run.
                if not query:
                    if not getattr(provider, "fetch_complete", True):
                        logger.warning(
                            "Provider %s reported an incomplete fetch; skipping expiration to avoid "
                            "deleting jobs that are still live.",
                            provider.provider_name,
                        )
                    else:
                        expired_ids = existing_active_ids - current_fetch_ids
                        if expired_ids:
                            delete_expired_jobs(provider.provider_name, list(expired_ids))
                            stats.expired += len(expired_ids)
                    
            except Exception as e:
                logger.exception("Error during ingestion for provider %s: %s", provider.provider_name, e)
                stats.failed += 1

        logger.info("Ingestion workflow completed. Stats: %s", stats.model_dump())
        return stats
