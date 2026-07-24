from typing import List
from datetime import datetime, timezone
import uuid

from backend.services.job_providers.base import BaseJobProvider
from backend.models.job import NormalizedJob

class MockJobProvider(BaseJobProvider):
    """
    A mock provider for testing the Job Ingestion Workflow.
    """

    @property
    def provider_name(self) -> str:
        return "mock_provider"

    def fetch_jobs(self, query: str | None = None) -> List[NormalizedJob]:
        # Generating some fake jobs for testing
        now = datetime.now(timezone.utc)
        
        return [
            NormalizedJob(
                provider=self.provider_name,
                provider_job_id="mock-job-1",
                title="Software Engineer",
                company="TechCorp",
                location="San Francisco, CA",
                description="We are looking for a skilled Software Engineer to build scalable web applications.",
                skills=["Python", "FastAPI", "React"],
                employment_type="Full-time",
                salary="$120,000 - $150,000",
                posted_date=now,
                raw_payload={"original_id": "mock-job-1", "department": "Engineering"}
            ),
            NormalizedJob(
                provider=self.provider_name,
                provider_job_id="mock-job-2",
                title="Data Scientist",
                company="DataWorks",
                location="Remote",
                description="Join our team to build predictive models and analyze large datasets.",
                skills=["Python", "Machine Learning", "SQL"],
                employment_type="Full-time",
                salary="$130,000 - $160,000",
                posted_date=now,
                raw_payload={"original_id": "mock-job-2", "department": "Data"}
            ),
            NormalizedJob(
                provider=self.provider_name,
                provider_job_id="mock-job-3",
                title="Frontend Developer",
                company="Webify",
                location="New York, NY",
                description="Looking for a creative frontend developer with an eye for design.",
                skills=["JavaScript", "React", "CSS"],
                employment_type="Contract",
                salary="$90/hr",
                posted_date=now,
                raw_payload={"original_id": "mock-job-3", "department": "Design"}
            )
        ]
