"""
Greenhouse job board provider.

Endpoint (public, no auth):
    https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true

`content=true` is the whole point of using this over an aggregator: it returns
the complete, HTML-entity-encoded job description rather than a snippet.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, List

from backend.models.job import NormalizedJob
from backend.services.job_providers.ats_base import ATSBoardProvider, BoardCompany, infer_employment_type
from backend.services.text_cleaning import clean_job_description

logger = logging.getLogger(__name__)

BASE_URL = "https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true"


def _parse_timestamp(value: Any) -> datetime:
    if isinstance(value, str) and value:
        try:
            # Greenhouse sends e.g. "2026-08-11T14:22:07-04:00" and sometimes a
            # trailing Z, which fromisoformat only accepts on 3.11+ as +00:00.
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            pass
    return datetime.now(timezone.utc)


class GreenhouseProvider(ATSBoardProvider):
    vendor = "greenhouse"

    def board_url(self, company: BoardCompany) -> str:
        return BASE_URL.format(token=company.token)

    def parse_board(self, company: BoardCompany, payload: Any) -> List[NormalizedJob]:
        raw_jobs = payload.get("jobs", []) if isinstance(payload, dict) else []
        jobs: List[NormalizedJob] = []

        for raw in raw_jobs:
            job_id = raw.get("id")
            title = (raw.get("title") or "").strip()
            if job_id is None or not title:
                continue

            # `content` arrives double-encoded (&lt;p&gt;...); clean_job_description
            # unescapes twice and strips markup, which handles exactly that case.
            description = clean_job_description(raw.get("content"))

            location = None
            location_obj = raw.get("location")
            if isinstance(location_obj, dict):
                location = location_obj.get("name")
            elif isinstance(location_obj, str):
                location = location_obj
            if not location:
                offices = [o.get("name") for o in raw.get("offices") or [] if isinstance(o, dict) and o.get("name")]
                location = ", ".join(offices) if offices else None

            try:
                jobs.append(
                    NormalizedJob(
                        provider=self.provider_name,
                        # Namespaced by board token: Greenhouse ids are unique per
                        # board, not globally, so two companies can collide.
                        provider_job_id=f"{company.token}:{job_id}",
                        title=title,
                        company=company.name,
                        location=location,
                        description=description,
                        skills=self.skills_for(description),
                        employment_type=infer_employment_type(title),
                        salary=None,  # Greenhouse exposes pay only via per-job metadata, inconsistently.
                        posted_date=_parse_timestamp(raw.get("first_published") or raw.get("updated_at")),
                        url=raw.get("absolute_url"),
                        raw_payload=raw,
                    )
                )
            except Exception as exc:
                logger.warning("Error normalizing Greenhouse job %s/%s: %s", company.token, job_id, exc)

        return jobs
