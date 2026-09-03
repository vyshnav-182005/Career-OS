from abc import ABC, abstractmethod
from typing import List
from backend.models.job import NormalizedJob

class BaseJobProvider(ABC):
    """
    Common interface for all job providers.
    Each provider is responsible for fetching jobs and converting them into the NormalizedJob schema.
    """

    # Whether the last fetch_jobs() call saw the provider's *entire* inventory.
    #
    # Ingestion expires any active job that a full (unqueried) fetch didn't
    # return, on the assumption that a missing job is a closed job. That
    # assumption breaks for providers that fan out over many endpoints - one
    # ATS board timing out would silently delete every job from that company.
    # A provider that only partially succeeded sets this False, and ingestion
    # skips expiration for that run rather than deleting live jobs.
    fetch_complete: bool = True

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Returns the unique name of the provider."""
        pass

    @abstractmethod
    def fetch_jobs(self, query: str | None = None) -> List[NormalizedJob]:
        """
        Fetches jobs from the provider and returns a list of NormalizedJob.
        Optionally filters by query.
        """
        pass
