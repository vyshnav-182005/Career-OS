"""
Lever job board provider.

Endpoint (public, no auth):
    https://api.lever.co/v0/postings/{token}?mode=json

Lever splits a posting across several fields - an intro `description`, a set of
titled `lists` (Requirements, What you'll do, ...), and a closing `additional`
section. Only the concatenation is the real job description, so this provider
reassembles them before cleaning.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, List

from backend.models.job import NormalizedJob
from backend.services.job_providers.ats_base import ATSBoardProvider, BoardCompany, infer_employment_type
from backend.services.text_cleaning import clean_job_description

logger = logging.getLogger(__name__)

BASE_URL = "https://api.lever.co/v0/postings/{token}?mode=json"

# Lever's free-text commitment field -> our employment_type vocabulary.
_COMMITMENT_MAP = {
    "full-time": "full_time",
    "full time": "full_time",
    "part-time": "part_time",
    "part time": "part_time",
    "intern": "internship",
    "internship": "internship",
    "contract": "contract",
    "contractor": "contract",
    "temporary": "contract",
    "freelance": "contract",
}


def _parse_timestamp(value: Any) -> datetime:
    # Lever sends createdAt as epoch milliseconds.
    if isinstance(value, (int, float)) and value > 0:
        try:
            return datetime.fromtimestamp(value / 1000, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            pass
    return datetime.now(timezone.utc)


def _first_location(all_locations: Any) -> str | None:
    if isinstance(all_locations, list) and all_locations:
        return str(all_locations[0])
    return None


def _assemble_description(raw: dict) -> str:
    parts: List[str] = []

    if raw.get("description"):
        parts.append(str(raw["description"]))

    for section in raw.get("lists") or []:
        if not isinstance(section, dict):
            continue
        heading = (section.get("text") or "").strip()
        content = section.get("content") or ""
        if heading:
            parts.append(f"<p>{heading}</p>")
        if content:
            parts.append(str(content))

    if raw.get("additional"):
        parts.append(str(raw["additional"]))

    return clean_job_description("\n".join(parts))


class LeverProvider(ATSBoardProvider):
    vendor = "lever"

    def board_url(self, company: BoardCompany) -> str:
        return BASE_URL.format(token=company.token)

    def parse_board(self, company: BoardCompany, payload: Any) -> List[NormalizedJob]:
        raw_jobs = payload if isinstance(payload, list) else []
        jobs: List[NormalizedJob] = []

        for raw in raw_jobs:
            if not isinstance(raw, dict):
                continue
            job_id = raw.get("id")
            title = (raw.get("text") or "").strip()
            if not job_id or not title:
                continue

            categories = raw.get("categories") or {}
            if not isinstance(categories, dict):
                categories = {}

            description = _assemble_description(raw)

            commitment = (categories.get("commitment") or "").strip()
            employment_type = _COMMITMENT_MAP.get(commitment.lower()) or infer_employment_type(title, commitment)

            try:
                jobs.append(
                    NormalizedJob(
                        provider=self.provider_name,
                        # Lever ids are already UUIDs, but namespacing keeps the
                        # id format consistent with the other ATS providers and
                        # makes a job's source board readable at a glance.
                        provider_job_id=f"{company.token}:{job_id}",
                        title=title,
                        company=company.name,
                        location=categories.get("location") or _first_location(categories.get("allLocations")),
                        description=description,
                        skills=self.skills_for(description),
                        employment_type=employment_type,
                        salary=_format_salary(raw.get("salaryRange")),
                        posted_date=_parse_timestamp(raw.get("createdAt")),
                        url=raw.get("hostedUrl") or raw.get("applyUrl"),
                        raw_payload=raw,
                    )
                )
            except Exception as exc:
                logger.warning("Error normalizing Lever job %s/%s: %s", company.token, job_id, exc)

        return jobs


def _format_salary(salary_range: Any) -> str | None:
    """Lever's optional salaryRange -> the free-text string our schema stores."""
    if not isinstance(salary_range, dict):
        return None
    minimum, maximum = salary_range.get("min"), salary_range.get("max")
    currency = salary_range.get("currency") or ""
    interval = (salary_range.get("interval") or "").replace("per-", "per ")
    if minimum and maximum:
        text = f"{currency} {minimum:,} - {maximum:,}".strip()
    elif minimum or maximum:
        text = f"{currency} {minimum or maximum:,}".strip()
    else:
        return None
    return f"{text} {interval}".strip()
