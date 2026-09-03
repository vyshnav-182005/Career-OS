"""
Job Matching Agent: the LLM verification layer on top of Phase 2's hybrid
retrieval (backend/services/job_matching.py). Retrieval already made unrelated
role families and skill sets unreachable via hard gates - this agent catches
the near-misses structural scoring cannot see, e.g. a job in the right family
that still demands years of a framework the candidate has never touched.

The agent filters further, never wider: it never sees a job retrieval already
excluded, and a failed/unavailable LLM call falls back to the Phase 2 feature
ranking rather than breaking the endpoint.
"""

import asyncio
import json
import logging
import re
from typing import Any, Optional

from openai import OpenAI
from pydantic import BaseModel

from backend.config import settings
from backend.db.supabase_client import (
    get_cached_job_matches,
    get_profile_data,
    get_profile_version,
    upsert_job_matches,
)
from backend.models.job import MatchedJob
from backend.services import taxonomy
from backend.services.job_matching import ScoredFeatures, ScoredJob

logger = logging.getLogger(__name__)

# Top-N candidates from Phase 2 that get sent for verification per request.
TOP_CANDIDATES = 25
# Candidates per LLM call. Smaller than TOP_CANDIDATES on purpose: an 8B model
# batching all 25 in one call was observed cross-attributing skills between
# jobs (rejecting a job for lacking a skill the candidate's own profile
# listed as a must-have). Chunks run concurrently, so a smaller BATCH_SIZE
# costs little in wall-clock time - measured live, batch=8 cut the error rate
# from ~14/25 to ~1/25; batch=4 is a further step in the same direction.
BATCH_SIZE = 4
# Bounds each chunk's blocking LLM call in the request path; a slower
# response falls back to feature ranking for that chunk immediately and
# retries in the background instead.
LLM_TIMEOUT_SECONDS = 20.0
DESCRIPTION_TRUNCATE = 600

_VALID_VERDICTS = {"strong", "possible", "reject"}

JOB_MATCHING_PROMPT = """\
You are a Job Matching Agent. You review a shortlist of jobs that already passed hard \
family/skill retrieval filters, and catch near-misses that structural scoring cannot see \
- e.g. a job in the right family that still demands years of a framework the candidate \
has never touched, or a title that reads well but whose actual responsibilities don't fit.

Return a JSON object matching EXACTLY this schema (no markdown, no extra text):
{{
  "results": [
    {{
      "index": 0,
      "verdict": "strong | possible | reject",
      "score": 0-100,
      "reason": "one sentence explaining the verdict",
      "matched_skills": ["skill the candidate has that this job wants"],
      "missing_skills": ["skill this job wants that the candidate doesn't show"]
    }}
  ]
}}

Rules:
1. Return exactly one result per job listed below, in the same order, with "index" matching \
the job's number (0-based).
2. verdict: "strong" = clearly a good fit; "possible" = plausible but with real gaps worth \
flagging; "reject" = it passed retrieval but the actual requirements are a genuine mismatch \
(e.g. years of a core skill the candidate has never used).
3. score: your own 0-100 confidence in the match.
4. reason: one concrete sentence grounded in the candidate's actual background and this \
job's actual requirements. Never invent details about either.
5. matched_skills / missing_skills: use the candidate's and job's own skill names, not \
synonyms you invent.
6. Before finalizing each job's verdict, reason, and missing_skills, re-check them against \
the Candidate's must_have_skills and nice_to_have_skills listed below - never claim the \
candidate lacks a skill that literally appears in either list. Evaluate and write each \
job's result independently; do not reuse or adapt wording, missing_skills, or a reason from \
another job in this list even when their requirements look similar.
7. Return ONLY valid JSON.

Candidate:
{profile_summary}

Jobs:
{jobs_block}
"""


class RankedJob(BaseModel):
    job: MatchedJob
    features: ScoredFeatures
    verdict: str
    score: float
    reason: str
    matched_skills: list[str]
    missing_skills: list[str]
    retrieval_sources: list[str]


def _build_profile_summary(profile_data: Optional[dict]) -> str:
    profile_data = profile_data or {}
    search_intent = profile_data.get("search_intent") or {}
    original = profile_data.get("original_resume") or {}
    summary = {
        "seniority": search_intent.get("seniority"),
        "strengths": profile_data.get("strengths", []),
        "must_have_skills": search_intent.get("must_have_skills", []),
        "nice_to_have_skills": search_intent.get("nice_to_have_skills", []),
        "recent_titles": [e.get("title") for e in (original.get("experience") or [])[:5] if e.get("title")],
    }
    return json.dumps(summary, indent=2)


def _build_jobs_block(candidates: list[ScoredJob]) -> str:
    lines = []
    for i, c in enumerate(candidates):
        job = c.job
        description = (job.description or "")[:DESCRIPTION_TRUNCATE]
        lines.append(
            f"{i}. Title: {job.title} | Company: {job.company} | "
            f"Skills: {', '.join(job.skills or [])}\nDescription: {description}"
        )
    return "\n\n".join(lines)


# Deliberately settings.model (the 8B default), not the 70B model used for
# resume optimization: measured live, meta/llama-3.1-70b-instruct's latency
# for this workload ranged ~6s-60s+/timeout for the same batch size - too
# inconsistent to block a user-facing request on. 8B is reliably fast
# (~6-10s for a 25-job request); BATCH_SIZE below is tuned small instead to
# control the cross-job skill-attribution errors 8B is prone to.
JOB_MATCHING_MODEL = settings.model


async def _call_llm(prompt: str) -> str:
    client = OpenAI(
        base_url="https://integrate.api.nvidia.com/v1",
        api_key=settings.nvidia_api_key,
        timeout=60.0,
        max_retries=1,
    )

    def _sync():
        completion = client.chat.completions.create(
            model=JOB_MATCHING_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": "You are a Job Matching Agent. Always respond with valid JSON only, no markdown.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            max_tokens=4096,
            response_format={"type": "json_object"},
        )
        return completion.choices[0].message.content or ""

    return await asyncio.to_thread(_sync)


def _parse_llm_results(raw_text: str, expected_count: int) -> Optional[list[dict]]:
    """Whole-response validation: a JSON parse failure or a result count that
    doesn't match the jobs sent is treated as fully malformed, not partially
    trusted, since the index-to-job mapping can no longer be relied on."""
    try:
        cleaned = raw_text.strip()
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        data = json.loads(cleaned)
        results = data.get("results")
        if not isinstance(results, list) or len(results) != expected_count:
            return None
        return results
    except Exception:
        return None


def _ranked_from_llm_entry(scored: ScoredJob, entry: Any, resume_skills: set[str]) -> Optional[RankedJob]:
    """Per-entry validation on top of the whole-response check above; a
    malformed single entry falls back individually rather than discarding
    the rest of an otherwise-valid batch."""
    if not isinstance(entry, dict):
        return None
    verdict = entry.get("verdict")
    if verdict not in _VALID_VERDICTS:
        return None
    try:
        score = max(0, min(100, int(entry.get("score", 0))))
    except (TypeError, ValueError):
        return None
    reason = entry.get("reason")
    matched = entry.get("matched_skills")
    missing = entry.get("missing_skills")
    if not isinstance(reason, str) or not isinstance(matched, list) or not isinstance(missing, list):
        return None
    return RankedJob(
        job=scored.job,
        features=scored.features,
        verdict=verdict,
        score=float(score),
        reason=reason,
        matched_skills=[s for s in matched if isinstance(s, str)],
        missing_skills=_drop_hallucinated_missing_skills(
            [s for s in missing if isinstance(s, str)], resume_skills, scored.job.id
        ),
        retrieval_sources=scored.retrieval_sources,
    )


def _drop_hallucinated_missing_skills(
    missing_skills: list[str], resume_skills: set[str], job_id: Optional[str]
) -> list[str]:
    """
    Deterministic guard on top of the LLM's own output: measured live, the
    model sometimes lists a skill as missing that's literally in the
    candidate's must_have/nice_to_have skills (a cross-job attribution error
    that persisted across model and batch-size changes). Never trust that
    claim over the candidate's own profile - free-text `reason` prose can't
    be corrected this way, but the structured missing_skills list (what the
    UI renders as "you'd need: ...") can be, at zero extra latency.
    """
    corrected = []
    for skill in missing_skills:
        canonical = taxonomy.canonicalize_skills([skill])
        if canonical and canonical[0] in resume_skills:
            logger.warning(
                "Dropping hallucinated missing_skill '%s' for job_id=%s - present in candidate's own skills",
                skill, job_id,
            )
            continue
        corrected.append(skill)
    return corrected


def _ranked_from_cache_row(scored: ScoredJob, row: dict) -> RankedJob:
    return RankedJob(
        job=scored.job,
        features=scored.features,
        verdict=row.get("verdict") or "possible",
        score=float(row.get("score") or 0),
        reason=row.get("reason") or "",
        matched_skills=row.get("matched_skills") or [],
        missing_skills=row.get("missing_skills") or [],
        retrieval_sources=scored.retrieval_sources,
    )


def _fallback_ranked_job(scored: ScoredJob, resume_skills: set[str]) -> RankedJob:
    """Feature-ranking fallback used when the LLM is unavailable, malformed,
    or too slow. Never returns 'reject' - retrieval already filtered this job
    to a real candidate, so an unreachable LLM must not silently drop it."""
    job_skills = set(taxonomy.canonicalize_skills(scored.job.skills or []))
    matched = sorted(job_skills & resume_skills)
    missing = sorted(job_skills - resume_skills)
    verdict = "strong" if scored.score >= 0.6 else "possible"
    return RankedJob(
        job=scored.job,
        features=scored.features,
        verdict=verdict,
        score=round(scored.score * 100),
        reason=(
            "Ranked from retrieval signals (semantic similarity, skill overlap, "
            "seniority, recency) - the AI reviewer was unavailable for this job."
        ),
        matched_skills=matched,
        missing_skills=missing,
        retrieval_sources=scored.retrieval_sources,
    )


def _resume_skills(profile_data: Optional[dict]) -> set[str]:
    search_intent = (profile_data or {}).get("search_intent") or {}
    raw = (search_intent.get("must_have_skills") or []) + (search_intent.get("nice_to_have_skills") or [])
    return set(taxonomy.canonicalize_skills(raw))


def _to_row(user_id: str, job_id: str, ranked: RankedJob, profile_version: str) -> dict:
    return {
        "user_id": user_id,
        "job_id": job_id,
        "verdict": ranked.verdict,
        "score": ranked.score,
        "reason": ranked.reason,
        "matched_skills": ranked.matched_skills,
        "missing_skills": ranked.missing_skills,
        "profile_version": profile_version,
        "feature_scores": ranked.features.model_dump(),
    }


async def _rank_with_llm(
    candidates: list[ScoredJob], profile_data: Optional[dict], timeout: Optional[float]
) -> Optional[list[RankedJob]]:
    """Runs a single LLM call for one chunk of `candidates` (at most
    BATCH_SIZE) and returns one RankedJob per candidate (falling back
    per-entry on partial malformation), or None if the whole response was
    unusable."""
    prompt = JOB_MATCHING_PROMPT.format(
        profile_summary=_build_profile_summary(profile_data),
        jobs_block=_build_jobs_block(candidates),
    )
    try:
        if timeout is not None:
            raw = await asyncio.wait_for(_call_llm(prompt), timeout=timeout)
        else:
            raw = await _call_llm(prompt)
    except asyncio.TimeoutError:
        logger.warning("Job matching LLM call timed out for %d jobs", len(candidates))
        return None
    except Exception:
        logger.exception("Job matching LLM call failed for %d jobs", len(candidates))
        return None

    entries = _parse_llm_results(raw, len(candidates))
    if entries is None:
        logger.warning("Job matching LLM response malformed or count mismatch for %d jobs", len(candidates))
        return None

    resume_skills = _resume_skills(profile_data)
    return [
        _ranked_from_llm_entry(c, entry, resume_skills) or _fallback_ranked_job(c, resume_skills)
        for c, entry in zip(candidates, entries)
    ]


def _chunk(items: list, size: int) -> list[list]:
    return [items[i:i + size] for i in range(0, len(items), size)]


async def _rank_chunk(
    chunk: list[ScoredJob], profile_data: Optional[dict], timeout: Optional[float]
) -> tuple[list[RankedJob], bool]:
    """Ranks one BATCH_SIZE-sized chunk. Returns (results, used_llm) - used_llm
    is False when this chunk's call failed/timed out/was malformed and every
    result in it is a feature-ranking fallback instead."""
    result = await _rank_with_llm(chunk, profile_data, timeout)
    if result is not None:
        return result, True
    resume_skills = _resume_skills(profile_data)
    return [_fallback_ranked_job(c, resume_skills) for c in chunk], False


async def _rank_candidates(
    candidates: list[ScoredJob], profile_data: Optional[dict], timeout: Optional[float]
) -> tuple[list[RankedJob], list[ScoredJob]]:
    """
    Splits `candidates` into BATCH_SIZE-sized chunks and ranks each with its
    own concurrent LLM call - smaller than one call for the whole shortlist
    so an 8B model has less to cross-attribute skills between within a call.
    Always returns one RankedJob per candidate, in order, plus the subset
    that fell back (for the caller to optionally retry in the background).
    """
    if not candidates:
        return [], []
    chunk_results = await asyncio.gather(
        *(_rank_chunk(chunk, profile_data, timeout) for chunk in _chunk(candidates, BATCH_SIZE))
    )
    ranked: list[RankedJob] = []
    fell_back: list[ScoredJob] = []
    for (results, used_llm), chunk in zip(chunk_results, _chunk(candidates, BATCH_SIZE)):
        ranked.extend(results)
        if not used_llm:
            fell_back.extend(chunk)
    return ranked, fell_back


async def _background_refresh_matches(
    user_id: str, candidates: list[ScoredJob], profile_data: Optional[dict], profile_version: str
) -> None:
    """Retries the LLM ranking (no request-path timeout) for jobs that fell
    back to feature ranking, and persists whatever comes back so the next
    request for this user can hit the cache. Best-effort: failures here must
    never surface anywhere, since nothing is awaiting this."""
    try:
        ranked, _ = await _rank_candidates(candidates, profile_data, timeout=None)
        rows = [
            _to_row(user_id, c.job.id, rj, profile_version)
            for c, rj in zip(candidates, ranked)
            if c.job.id
        ]
        upsert_job_matches(rows)
    except Exception:
        logger.exception("Background job-match refresh failed for user_id=%s", user_id)


async def rank_jobs(
    user_id: str,
    candidates: list[ScoredJob],
    profile_data: Optional[dict] = None,
    background_tasks: Any = None,
) -> list[RankedJob]:
    """
    Verifies the top Phase 2 candidates in small concurrent LLM batches, using
    the job_matches cache (keyed on profile_version) to skip jobs already
    scored since the profile last changed. On LLM failure/timeout/malformed
    output, falls back to Phase 2 feature ranking for the affected jobs only
    - the LLM is an enhancement, never a hard dependency.
    """
    if not candidates:
        return []
    candidates = candidates[:TOP_CANDIDATES]

    if profile_data is None:
        profile_data = get_profile_data(user_id)
    profile_version = get_profile_version(user_id)

    job_ids = [c.job.id for c in candidates if c.job.id]
    cached = get_cached_job_matches(user_id, job_ids, profile_version)

    ranked: list[Optional[RankedJob]] = [None] * len(candidates)
    miss_indices: list[int] = []
    for i, c in enumerate(candidates):
        row = cached.get(c.job.id) if c.job.id else None
        if row:
            ranked[i] = _ranked_from_cache_row(c, row)
        else:
            miss_indices.append(i)

    if miss_indices:
        miss_candidates = [candidates[i] for i in miss_indices]
        llm_ranked, fell_back = await _rank_candidates(miss_candidates, profile_data, timeout=LLM_TIMEOUT_SECONDS)
        for i, rj in zip(miss_indices, llm_ranked):
            ranked[i] = rj

        if fell_back and profile_version and background_tasks is not None:
            background_tasks.add_task(
                _background_refresh_matches, user_id, fell_back, profile_data, profile_version
            )

        if profile_version:
            to_persist = [
                _to_row(user_id, candidates[i].job.id, ranked[i], profile_version)
                for i in miss_indices
                if candidates[i].job.id and ranked[i] is not None
            ]
            if to_persist:
                upsert_job_matches(to_persist)

    return [rj for rj in ranked if rj is not None]


def select_top_matches(ranked: list[RankedJob], top_n: int = 10) -> list[RankedJob]:
    """Drops every 'reject' verdict and returns the top-scoring survivors.
    The agent filters further than Phase 2, never wider - nothing dropped
    here can come back."""
    survivors = [rj for rj in ranked if rj.verdict != "reject"]
    survivors.sort(key=lambda rj: rj.score, reverse=True)
    return survivors[:top_n]
