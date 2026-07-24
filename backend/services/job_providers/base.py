from abc import ABC, abstractmethod
from typing import List
from backend.models.job import NormalizedJob

class BaseJobProvider(ABC):
    """
    Common interface for all job providers.
    Each provider is responsible for fetching jobs and converting them into the NormalizedJob schema.
    """
    
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
