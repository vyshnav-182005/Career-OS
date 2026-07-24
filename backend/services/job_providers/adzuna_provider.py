import requests
from typing import List, Optional
from datetime import datetime, timezone
import logging

from backend.services.job_providers.base import BaseJobProvider
from backend.models.job import NormalizedJob
from backend.config import settings

logger = logging.getLogger(__name__)

class AdzunaProvider(BaseJobProvider):
    """
    Fetches jobs from Adzuna API.
    """

    @property
    def provider_name(self) -> str:
        return "adzuna"

    def fetch_jobs(self, query: str | None = None) -> List[NormalizedJob]:
        app_id = settings.adzuna_app_id
        app_key = settings.adzuna_app_key
        if not app_id or not app_key:
            logger.info("Adzuna API credentials (ADZUNA_APP_ID / ADZUNA_APP_KEY) not configured — skipping.")
            return []


        url = "https://api.adzuna.com/v1/api/jobs/us/search/1"
        params = {
            "app_id": app_id,
            "app_key": app_key,
            "results_per_page": 50,
        }
        if query:
            params["what"] = query

        try:
            response = requests.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            jobs = data.get("results", [])
        except Exception as e:
            logger.error("Failed to fetch jobs from Adzuna: %s", e)
            return []

        normalized_jobs = []
        for job in jobs:
            try:
                posted_date = None
                if "created" in job:
                    try:
                        # Adzuna format: 2023-10-25T14:49:12Z
                        posted_date = datetime.fromisoformat(job["created"].replace('Z', '+00:00'))
                    except ValueError:
                        pass

                skills = []
                if job.get("category", {}).get("label"):
                    skills.append(job["category"]["label"])

                company_name = job.get("company", {}).get("display_name", "Unknown Company")
                location = ", ".join(job.get("location", {}).get("area", [])) or "Remote"
                
                normalized_jobs.append(
                    NormalizedJob(
                        provider=self.provider_name,
                        provider_job_id=str(job.get("id")),
                        title=job.get("title", "Unknown Title"),
                        company=company_name,
                        location=location,
                        description=job.get("description", ""),
                        skills=skills,
                        employment_type=job.get("contract_time", "full_time"),
                        salary=str(job.get("salary_min", "")),
                        posted_date=posted_date or datetime.now(timezone.utc),
                        url=job.get("redirect_url"),
                        raw_payload=job
                    )
                )
            except Exception as e:
                logger.warning("Error normalizing Adzuna job %s: %s", job.get("id"), e)

        return normalized_jobs
