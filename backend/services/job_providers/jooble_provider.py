import requests
from typing import List, Optional
from datetime import datetime, timezone
import logging

from backend.services.job_providers.base import BaseJobProvider
from backend.models.job import NormalizedJob
from backend.services import taxonomy
from backend.config import settings

logger = logging.getLogger(__name__)

class JoobleProvider(BaseJobProvider):
    """
    Fetches jobs from Jooble API.
    """

    @property
    def provider_name(self) -> str:
        return "jooble"

    def fetch_jobs(self, query: str | None = None) -> List[NormalizedJob]:
        api_key = settings.job_api_key_2
        if not api_key:
            logger.warning("Jooble API key (JOOBLE_API_KEY) is not configured.")
            return []

        url = f"https://jooble.org/api/{api_key}"
        
        payload = {}
        if query:
            payload["keywords"] = query

        try:
            response = requests.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
            jobs = data.get("jobs", [])
        except Exception as e:
            logger.error("Failed to fetch jobs from Jooble: %s", e)
            return []

        normalized_jobs = []
        for job in jobs:
            try:
                posted_date = None
                if "updated" in job:
                    try:
                        posted_date = datetime.fromisoformat(job["updated"].replace('Z', '+00:00'))
                    except ValueError:
                        pass
                
                normalized_jobs.append(
                    NormalizedJob(
                        provider=self.provider_name,
                        provider_job_id=str(job.get("id")),
                        title=job.get("title", "Unknown Title"),
                        company=job.get("company", "Unknown Company"),
                        location=job.get("location", "Remote"),
                        description=job.get("snippet", ""),
                        # Jooble returns no skills field of its own, and leaving
                        # this empty zeroes the skill_overlap feature for every
                        # job it supplies - which is most of the non-software
                        # inventory. The ATS providers already mine their
                        # description the same way; the snippet is shorter, so
                        # this yields less, but not nothing.
                        skills=taxonomy.extract_skills(job.get("snippet", "")),
                        employment_type="full_time", # Jooble doesn't typically provide this in simple search
                        salary=str(job.get("salary", "")),
                        posted_date=posted_date or datetime.now(timezone.utc),
                        url=job.get("link"),
                        raw_payload=job
                    )
                )
            except Exception as e:
                logger.warning("Error normalizing Jooble job %s: %s", job.get("id"), e)

        return normalized_jobs
