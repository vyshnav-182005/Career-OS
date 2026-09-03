from enum import Enum
from typing import List, Optional, Any, Dict
from datetime import datetime
from pydantic import BaseModel, Field

class JobStatus(str, Enum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    EXPIRED = "EXPIRED"

class NormalizedJob(BaseModel):
    """
    Standardized schema that every provider must conform to.
    """
    provider: str
    provider_job_id: str
    title: str
    company: str
    location: Optional[str] = None
    description: Optional[str] = None
    skills: List[str] = Field(default_factory=list)
    employment_type: Optional[str] = None
    salary: Optional[str] = None
    posted_date: Optional[datetime] = None
    
    # We store the original payload from the provider for debugging/future extraction
    raw_payload: Optional[Dict[str, Any]] = None
    
    # Semantic embedding vector
    embedding: Optional[List[float]] = None

    # External apply URL
    url: Optional[str] = None

    # Job-matching taxonomy (Phase 1)
    role_family: Optional[str] = None
    source_query: Optional[str] = None
    last_seen_at: Optional[datetime] = None
    content_hash: Optional[str] = None

class MatchedJob(NormalizedJob):
    """
    Schema for a job returned from vector similarity search.
    """
    # Present once persisted (every match_jobs*/search_jobs_fulltext row); absent
    # on a NormalizedJob that hasn't been upserted yet.
    id: Optional[str] = None
    similarity: Optional[float] = None

class JobFilter(BaseModel):
    """
    Schema for filtering active jobs.
    """
    title: Optional[str] = None
    location: Optional[str] = None
    company: Optional[str] = None
    employment_type: Optional[str] = None
    skills: Optional[List[str]] = None

class IngestionStatistics(BaseModel):
    fetched: int = 0
    inserted: int = 0
    updated: int = 0
    skipped: int = 0
    expired: int = 0
    failed: int = 0
