"""
Hybrid job retrieval: replaces single-vector kNN with three fused retrievers
(vector, lexical, title-family) gated by hard SQL predicates on role_family,
then scored on named, individually-inspectable features. A job in an excluded
or off-target family is unreachable here regardless of embedding similarity -
that's the whole point of this rewrite (see .agents/job-matching-rework-prompts.md).
"""

import logging
import re
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel

from backend.db.supabase_client import (
    get_cached_profile_embedding,
    get_jobs_by_role_family,
    get_profile_data,
    match_jobs_v2,
    search_jobs_fulltext,
)
from backend.models.job import MatchedJob
from backend.models.profile import SearchIntent
from backend.services import taxonomy
from backend.services.embeddings import generate_profile_embedding

logger = logging.getLogger(__name__)

# Returned by the vector leg when the profile has no embedding at all, which
# the caller must surface as an error rather than backfill. Distinct from an
# empty or null result, which just means that retriever found nothing.
_NO_EMBEDDING = object()

# Candidates requested per retriever before fusion.
CANDIDATE_POOL_SIZE = 60
# Reciprocal Rank Fusion constant - larger k flattens the influence of rank
# differences between retrievers; 60 is RRF's usual default.
RRF_K = 60
# Cap on the fused pool that actually gets feature-scored, bounding the cost
# of the canonicalize_skills calls below for a normal handful-of-hundreds pool.
CANDIDATE_POOL_LIMIT = 120
# Jobs below this weighted score are dropped even though they survived retrieval.
MIN_SCORE = 0.35
# Final number of results returned.
RESULT_COUNT = 40
# Linear recency decay window.
RECENCY_WINDOW_DAYS = 45

# Weighted sum of the five named features below into ScoredJob.score. Tune by
# hand; these are the only "black box" knobs in retrieval.
WEIGHTS = {
    "semantic": 0.40,       # cosine similarity between profile and job text, normalized 0-1
    "skill_overlap": 0.25,  # canonicalized overlap: |resume skills ∩ job skills| / max(1, |job skills|)
    "family_fit": 0.20,     # 1.0 exact role_family, 0.6 adjacent, 0.0 excluded/mismatched (hard-dropped, see below)
    "seniority_fit": 0.10,  # penalizes a title whose seniority is far from the profile's
    "recency": 0.05,        # linear decay to 0 over RECENCY_WINDOW_DAYS since posted_date
}

SENIORITY_ORDER = {"intern": 0, "junior": 1, "mid": 2, "senior": 3, "lead": 4}
_SENIOR_TITLE_RE = re.compile(r"\b(senior|staff|principal|lead|director|head of|manager)\b", re.IGNORECASE)
_JUNIOR_TITLE_RE = re.compile(r"\b(junior|intern|entry[\s-]?level|graduate|associate)\b", re.IGNORECASE)


class ScoredFeatures(BaseModel):
    semantic: float
    skill_overlap: float
    family_fit: float
    seniority_fit: float
    recency: float


class ScoredJob(BaseModel):
    job: MatchedJob
    features: ScoredFeatures
    score: float
    retrieval_sources: list[str]


def _coerce_search_intent(raw: Optional[dict]) -> SearchIntent:
    """
    Falls back to permissive defaults (no family/skill gating beyond what the
    embedding itself provides) when search_intent is missing - e.g. a profile
    created before the Phase-1 agent changes, or a malformed cached payload.
    """
    if not raw:
        return SearchIntent()
    try:
        return SearchIntent.model_validate(raw)
    except Exception:
        logger.warning("Invalid search_intent payload, using permissive defaults")
        return SearchIntent()


def _build_fts_query(terms: list[str]) -> str:
    """OR-joins terms for websearch_to_tsquery; multi-word terms are quoted as phrases."""
    if not terms:
        return ""
    quoted = [f'"{t}"' if " " in t else t for t in terms]
    return " OR ".join(quoted)


def _merge_candidates(
    labeled: dict[str, list[dict[str, Any]]]
) -> tuple[dict[str, dict[str, Any]], dict[str, list[str]]]:
    jobs_by_id: dict[str, dict[str, Any]] = {}
    sources_by_id: dict[str, list[str]] = defaultdict(list)
    for source, jobs in labeled.items():
        for job in jobs:
            job_id = job.get("id")
            if not job_id:
                continue
            jobs_by_id.setdefault(job_id, job)
            sources_by_id[job_id].append(source)
    return jobs_by_id, sources_by_id


def _reciprocal_rank_fusion(ranked_lists: list[list[dict[str, Any]]], k: int = RRF_K) -> dict[str, float]:
    scores: dict[str, float] = {}
    for ranked in ranked_lists:
        for rank, job in enumerate(ranked, start=1):
            job_id = job.get("id")
            if not job_id:
                continue
            scores[job_id] = scores.get(job_id, 0.0) + 1.0 / (k + rank)
    return scores


def _semantic(similarity: Optional[float]) -> float:
    """Cosine similarity is -1..1; jobs retrieved without one (lexical/title-family
    only) get a neutral middle score rather than being penalized for a signal
    that retriever never computes."""
    if similarity is None:
        return 0.5
    return max(0.0, min(1.0, (similarity + 1) / 2))


def _skill_overlap(job_skills: Optional[list[str]], resume_skills: list[str]) -> float:
    job_canonical = set(taxonomy.canonicalize_skills(job_skills or []))
    if not job_canonical:
        return 0.0
    resume_canonical = set(taxonomy.canonicalize_skills(resume_skills))
    return len(resume_canonical & job_canonical) / max(1, len(job_canonical))


def _family_fit(job_family: Optional[str], search_intent: SearchIntent) -> float:
    if job_family and job_family in search_intent.excluded_families:
        return 0.0
    if not search_intent.role_families:
        # No positive family signal to gate on (e.g. search_intent absent) -
        # not a hard drop, just an unweighted middle score.
        return 0.5
    if job_family is None:
        return 0.4
    if job_family in search_intent.role_families:
        return 1.0
    adjacent = {
        adj for family in search_intent.role_families for adj in taxonomy.ADJACENT_FAMILIES.get(family, [])
    }
    if job_family in adjacent:
        return 0.6
    return 0.0


def _job_seniority_level(title: str) -> Optional[int]:
    if not title:
        return None
    if _SENIOR_TITLE_RE.search(title):
        return 3
    if _JUNIOR_TITLE_RE.search(title):
        return 1
    return None


def _seniority_fit(title: str, search_intent: SearchIntent) -> float:
    job_level = _job_seniority_level(title)
    if job_level is None:
        # Title carries no seniority signal (e.g. plain "Backend Engineer") -
        # mild default rather than a penalty for information the title doesn't have.
        return 0.8
    profile_level = SENIORITY_ORDER.get(search_intent.seniority, 2)
    distance = abs(job_level - profile_level)
    return max(0.0, 1.0 - 0.35 * distance)


def _recency(posted_date: Any) -> float:
    if not posted_date:
        return 0.0
    if isinstance(posted_date, str):
        try:
            posted_date = datetime.fromisoformat(posted_date.replace("Z", "+00:00"))
        except ValueError:
            return 0.0
    if posted_date.tzinfo is None:
        posted_date = posted_date.replace(tzinfo=timezone.utc)
    days_old = (datetime.now(timezone.utc) - posted_date).days
    return max(0.0, 1.0 - days_old / RECENCY_WINDOW_DAYS)


def retrieve_candidates(user_id: str, profile_data: Optional[dict] = None) -> Optional[list[ScoredJob]]:
    """
    Full hybrid retrieval pipeline. Returns None only when the profile
    embedding is genuinely unavailable (distinct from a valid empty result,
    which is a plain empty list) - callers should surface that as an error
    state, never silently backfill it with unfiltered jobs.
    """
    if profile_data is None:
        profile_data = get_profile_data(user_id)
    if not profile_data:
        return []

    search_intent = _coerce_search_intent(profile_data.get("search_intent"))

    lexical_terms = search_intent.must_have_skills or search_intent.nice_to_have_skills
    fts_query = _build_fts_query(lexical_terms)

    # The three retrievers are independent of each other, and every one of them
    # is a round trip to a Supabase region that is not local - measured at
    # 0.26-0.72s each, which run back to back was the single largest block of
    # time in a warm /jobs/recommended. Only the vector search depends on the
    # embedding, so it is chained behind that lookup while the other two are
    # already in flight. Fusion below is order-independent, so this changes
    # timing only, never which jobs come back.
    def _vector_jobs():
        embedding = get_cached_profile_embedding(user_id)
        if not embedding:
            embedding = generate_profile_embedding(profile_data)
        if not embedding:
            # An explicit sentinel, not None: match_jobs_v2 returns whatever
            # PostgREST hands back, which can itself be None. Using None for
            # both would let a null RPC response be reported to the user as
            # "your profile has no embedding" and throw away the lexical and
            # title-family results that did come back.
            return _NO_EMBEDDING
        return match_jobs_v2(
            embedding,
            target_families=search_intent.role_families,
            excluded_families=search_intent.excluded_families,
            # NOT passed to SQL: job.skills is stored as raw provider text, never
            # canonicalized at ingest time, so a literal array-overlap filter here
            # would silently drop real matches on spelling alone ("reactjs" vs
            # "React"). skill_overlap below does the canonicalized comparison instead.
            must_have_skills=[],
            min_posted_date=None,
            # NOT passed to SQL: location string quality/format isn't validated
            # yet, so hard-gating on it risks empty results for the wrong reason.
            locations=[],
            match_threshold=0.0,
            match_count=CANDIDATE_POOL_SIZE,
        )

    with ThreadPoolExecutor(max_workers=3) as pool:
        vector_future = pool.submit(_vector_jobs)
        lexical_future = pool.submit(
            search_jobs_fulltext,
            fts_query,
            target_families=search_intent.role_families,
            match_count=CANDIDATE_POOL_SIZE,
        ) if fts_query else None
        title_family_future = pool.submit(
            get_jobs_by_role_family, search_intent.role_families, match_count=CANDIDATE_POOL_SIZE
        ) if search_intent.role_families else None

        vector_jobs = vector_future.result()
        lexical_jobs = (lexical_future.result() if lexical_future else []) or []
        title_family_jobs = (title_family_future.result() if title_family_future else []) or []

    if vector_jobs is _NO_EMBEDDING:
        return None
    vector_jobs = vector_jobs or []

    labeled = {"vector": vector_jobs, "lexical": lexical_jobs, "title_family": title_family_jobs}
    jobs_by_id, sources_by_id = _merge_candidates(labeled)
    fused_scores = _reciprocal_rank_fusion(list(labeled.values()))

    ranked_ids = sorted(fused_scores, key=fused_scores.get, reverse=True)[:CANDIDATE_POOL_LIMIT]
    resume_skills = search_intent.must_have_skills + search_intent.nice_to_have_skills

    scored: list[ScoredJob] = []
    for job_id in ranked_ids:
        job_dict = jobs_by_id[job_id]
        job_family = job_dict.get("role_family")

        family_fit = _family_fit(job_family, search_intent)
        if family_fit == 0.0:
            # Hard drop, not a low score - an excluded/mismatched family must
            # never claw back into results via a high semantic score.
            continue

        features = ScoredFeatures(
            semantic=_semantic(job_dict.get("similarity")),
            skill_overlap=_skill_overlap(job_dict.get("skills"), resume_skills),
            family_fit=family_fit,
            seniority_fit=_seniority_fit(job_dict.get("title", ""), search_intent),
            recency=_recency(job_dict.get("posted_date")),
        )
        score = sum(getattr(features, name) * weight for name, weight in WEIGHTS.items())
        if score < MIN_SCORE:
            continue

        try:
            job = MatchedJob.model_validate(job_dict)
        except Exception:
            logger.exception("Skipping malformed job row id=%s", job_id)
            continue

        scored.append(
            ScoredJob(job=job, features=features, score=score, retrieval_sources=sources_by_id[job_id])
        )

    scored.sort(key=lambda sj: sj.score, reverse=True)
    return scored[:RESULT_COUNT]
