"""
Shared machinery for ATS board providers (Greenhouse, Lever, and any vendor
added later).

An ATS board API is a different shape from a keyword aggregator like Jooble:

  - There is no search. You address one company's board at a time and get its
    entire current inventory back. Query filtering therefore happens here,
    client-side, rather than being pushed to the provider.
  - There is no discovery endpoint. The set of companies to poll is config -
    backend/data/ats_companies.json - not something the API can tell us.
  - There is no key. These endpoints are the public JSON behind every hosted
    careers page, which is why this path works with no credentials at all.

The payoff for that extra plumbing is the *full* job description. Aggregator
snippets are a few hundred characters, which quietly caps how well the ATS
scorer and the resume optimizer can do their jobs.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from abc import abstractmethod
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, NamedTuple, Optional, Sequence, Tuple

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from backend.models.job import NormalizedJob
from backend.services import taxonomy
from backend.services.job_providers.base import BaseJobProvider

logger = logging.getLogger(__name__)

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SEED_FILE = os.path.join(_BACKEND_DIR, "data", "ats_companies.json")


class BoardCompany(NamedTuple):
    token: str
    name: str


# --- Company seed list -------------------------------------------------------

_companies_lock = threading.Lock()
_companies_cache: Dict[str, List[BoardCompany]] = {}


def load_companies(vendor: str) -> List[BoardCompany]:
    """
    Reads the seeded board list for a vendor, cached after first read.
    A malformed or missing file yields an empty list (and a loud log) rather
    than taking ingestion down.
    """
    with _companies_lock:
        if vendor in _companies_cache:
            return _companies_cache[vendor]

        companies: List[BoardCompany] = []
        try:
            with open(SEED_FILE, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            seen: set[str] = set()
            for entry in data.get(vendor, []):
                token = (entry.get("token") or "").strip()
                if not token or token in seen:
                    continue
                seen.add(token)
                companies.append(BoardCompany(token=token, name=(entry.get("name") or token).strip()))
        except FileNotFoundError:
            logger.warning("ATS seed file not found at %s - %s provider has no boards to poll.", SEED_FILE, vendor)
        except (json.JSONDecodeError, AttributeError) as exc:
            logger.error("ATS seed file %s is malformed: %s", SEED_FILE, exc)

        _companies_cache[vendor] = companies
        return companies


def reload_companies() -> None:
    """Drops the seed cache so an edited ats_companies.json is picked up."""
    with _companies_lock:
        _companies_cache.clear()


# --- Per-vendor board cache --------------------------------------------------
#
# Ingestion is driven per preferred-role-title: /jobs/recommended kicks off one
# workflow run per role, and the scheduler loops over every distinct role in the
# system. For an aggregator that's one cheap keyword request each. For an ATS
# provider it would be a full fan-out across every seeded board, per role -
# hundreds of requests to fetch the exact same inventory. So the fan-out result
# is cached per vendor and the per-role query filter is applied over the cache.

_board_cache_lock = threading.Lock()
_board_cache: Dict[str, Tuple[float, List[NormalizedJob], bool]] = {}

BOARD_CACHE_TTL_SECONDS = 1800  # 30 minutes


def clear_board_cache() -> None:
    with _board_cache_lock:
        _board_cache.clear()


# --- Text helpers ------------------------------------------------------------

_INTERN_RE = re.compile(r"\b(intern|internship|co[\s-]?op|apprentice)\b", re.IGNORECASE)
_CONTRACT_RE = re.compile(r"\b(contract|contractor|freelance|temporary|fixed[\s-]term)\b", re.IGNORECASE)
_PART_TIME_RE = re.compile(r"\bpart[\s-]?time\b", re.IGNORECASE)

_STOPWORDS = {
    "a", "an", "and", "at", "engineer", "engineering", "for", "in", "of", "or",
    "senior", "junior", "staff", "lead", "principal", "the", "to", "with",
}
_WORD_RE = re.compile(r"[a-z0-9+#.]+")


def infer_employment_type(*texts: Optional[str], default: str = "full_time") -> str:
    """
    Neither Greenhouse nor Lever always states employment type, so it is
    inferred from the title (and commitment string, where present). Falls back
    to full_time, which is what the overwhelming majority of board postings are.
    """
    blob = " ".join(text for text in texts if text)
    if _INTERN_RE.search(blob):
        return "internship"
    if _PART_TIME_RE.search(blob):
        return "part_time"
    if _CONTRACT_RE.search(blob):
        return "contract"
    return default


def matches_query(title: str, query: str) -> bool:
    """
    Client-side stand-in for the keyword search an ATS board doesn't offer.

    Prefers the role-family taxonomy - the same gate the matching pipeline uses
    downstream - so "Backend Engineer" pulls in "Software Engineer, Platform"
    when both classify as `backend`, instead of only exact string matches. Falls
    back to meaningful word overlap when either side is unclassifiable.
    """
    if not query:
        return True
    if not title:
        return False

    query_family = taxonomy.classify_title(query)
    title_family = taxonomy.classify_title(title)
    if query_family and title_family:
        return query_family == title_family

    query_words = {word for word in _WORD_RE.findall(query.lower()) if word not in _STOPWORDS and len(word) > 2}
    if not query_words:
        return True
    title_words = set(_WORD_RE.findall(title.lower()))
    return bool(query_words & title_words)


def _build_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=2,
        backoff_factor=0.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET"]),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_maxsize=16)
    session.mount("https://", adapter)
    session.headers.update({"User-Agent": "CareerOS/1.0 (job ingestion)", "Accept": "application/json"})
    return session


# --- Provider base -----------------------------------------------------------

class ATSBoardProvider(BaseJobProvider):
    """
    Fans out across the seeded boards for one ATS vendor.

    Subclasses supply `vendor`, a URL builder, and a payload -> NormalizedJob
    mapping; everything else - concurrency, retries, caching, dedup, partial
    failure accounting, query filtering - lives here.
    """

    vendor: str = ""
    request_timeout: int = 15
    max_workers: int = 8

    def __init__(self, companies: Optional[Sequence[BoardCompany]] = None, use_cache: bool = True):
        self._companies_override = list(companies) if companies is not None else None
        self._use_cache = use_cache

    @property
    def provider_name(self) -> str:
        return self.vendor

    # -- subclass hooks --

    @abstractmethod
    def board_url(self, company: BoardCompany) -> str:
        """The public JSON endpoint for one company's board."""

    @abstractmethod
    def parse_board(self, company: BoardCompany, payload: Any) -> List[NormalizedJob]:
        """Turns one board's response body into NormalizedJob records."""

    # -- fetching --

    def companies(self) -> List[BoardCompany]:
        if self._companies_override is not None:
            return self._companies_override
        return load_companies(self.vendor)

    def fetch_jobs(self, query: str | None = None) -> List[NormalizedJob]:
        jobs, complete = self._all_jobs()
        self.fetch_complete = complete

        if not query:
            return jobs
        return [job for job in jobs if matches_query(job.title, query)]

    def _all_jobs(self) -> Tuple[List[NormalizedJob], bool]:
        cache_key = self.vendor
        if self._use_cache:
            with _board_cache_lock:
                cached = _board_cache.get(cache_key)
                if cached and (time.monotonic() - cached[0]) < BOARD_CACHE_TTL_SECONDS:
                    return cached[1], cached[2]

        jobs, complete = self._fan_out()

        if self._use_cache:
            with _board_cache_lock:
                _board_cache[cache_key] = (time.monotonic(), jobs, complete)
        return jobs, complete

    def _fan_out(self) -> Tuple[List[NormalizedJob], bool]:
        companies = self.companies()
        if not companies:
            # No boards configured means we learned nothing about this
            # provider's inventory. Reporting "complete" here would let
            # ingestion expire every job it has ever stored for the vendor.
            logger.warning("No %s boards configured in %s - nothing to fetch.", self.vendor, SEED_FILE)
            return [], False

        session = _build_session()
        collected: List[NormalizedJob] = []
        failed: List[str] = []

        try:
            with ThreadPoolExecutor(max_workers=min(self.max_workers, len(companies))) as pool:
                results = pool.map(lambda company: self._fetch_one(session, company), companies)
                for company, (ok, board_jobs) in zip(companies, results):
                    if ok:
                        collected.extend(board_jobs)
                    else:
                        failed.append(company.token)
        finally:
            session.close()

        # A board listed twice, or a vendor echoing a posting under two offices,
        # would otherwise reach upsert_jobs as duplicate rows for the same
        # (provider, provider_job_id) - which Postgres rejects outright with
        # "ON CONFLICT DO UPDATE command cannot affect row a second time".
        deduped: Dict[str, NormalizedJob] = {}
        for job in collected:
            deduped.setdefault(job.provider_job_id, job)

        complete = not failed
        if failed:
            logger.warning(
                "%s: %d of %d boards failed (%s%s). Skipping expiration for this run so live jobs aren't deleted.",
                self.vendor,
                len(failed),
                len(companies),
                ", ".join(failed[:8]),
                "..." if len(failed) > 8 else "",
            )

        logger.info(
            "%s: fetched %d jobs from %d/%d boards.",
            self.vendor, len(deduped), len(companies) - len(failed), len(companies),
        )
        return list(deduped.values()), complete

    def _fetch_one(self, session: requests.Session, company: BoardCompany) -> Tuple[bool, List[NormalizedJob]]:
        url = self.board_url(company)
        try:
            response = session.get(url, timeout=self.request_timeout)
        except requests.RequestException as exc:
            logger.warning("%s board %s unreachable: %s", self.vendor, company.token, exc)
            return False, []

        if response.status_code == 404:
            # A dead or renamed board token. Still counted as a failure: the
            # alternative is expiring that company's jobs on what may just be a
            # typo in the seed file. `scripts/verify_ats_boards.py --prune`
            # is how bad tokens get removed deliberately.
            logger.warning("%s board '%s' returned 404 - token may be wrong or the board retired.", self.vendor, company.token)
            return False, []

        if not response.ok:
            logger.warning("%s board %s returned HTTP %s", self.vendor, company.token, response.status_code)
            return False, []

        try:
            payload = response.json()
        except ValueError as exc:
            logger.warning("%s board %s returned non-JSON: %s", self.vendor, company.token, exc)
            return False, []

        try:
            return True, self.parse_board(company, payload)
        except Exception as exc:
            logger.exception("Failed to parse %s board %s: %s", self.vendor, company.token, exc)
            return False, []

    # -- shared normalization --

    @staticmethod
    def skills_for(description: str) -> List[str]:
        return taxonomy.extract_skills(description)
