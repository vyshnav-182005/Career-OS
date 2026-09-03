import logging
import re
from typing import Any, Dict, List, Optional

from backend.models.resume import Project
from backend.models.schemas import ATSScore, OptimizedProject
from backend.agents.ats_scoring_agent import run_ats_scoring
from backend.services import taxonomy
from backend.services.text_cleaning import clean_html_text

logger = logging.getLogger(__name__)

MAX_BULLETS_PER_PROJECT = 4
GROUNDING_OVERLAP_RATIO = 0.3
GROUNDING_MIN_OVERLAP_WORDS = 3

# Overall score weights (must sum to 1.0). Skills weighted highest since ATS
# systems are primarily keyword/skill matchers; project/experience relevance
# and education fill out the qualitative fit.
SKILL_WEIGHT = 0.40
PROJECT_WEIGHT = 0.20
EXPERIENCE_WEIGHT = 0.25
EDUCATION_WEIGHT = 0.15

# --- Quick (no-LLM) ATS match score, used for the job list ----------------
# compute_ats_score below costs one LLM call per job, which is fine on modal
# open but not for the 10-30 job cards rendered at once on the Jobs page.
# These weights drive a deterministic estimate built from signals retrieval
# has already computed, so every card can show a match percentage instantly.
# Must sum to 1.0.
QUICK_SKILL_WEIGHT = 0.55
QUICK_SEMANTIC_WEIGHT = 0.20
QUICK_FAMILY_WEIGHT = 0.15
QUICK_SENIORITY_WEIGHT = 0.10

# Below this many recognizable skills, a JD gives too thin a keyword signal to
# score confidently on skills alone, so the skill term is pulled toward the
# neutral middle instead of reporting a misleading 0% or 100%.
MIN_JD_SKILLS_FOR_CONFIDENCE = 3
# Characters of JD text mined for skill terms: enough to cover a requirements
# list without scanning legal/boilerplate footers.
JD_SKILL_SCAN_CHARS = 4000

_STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with", "by",
    "at", "as", "is", "are", "was", "were", "be", "been", "this", "that",
    "these", "those", "from", "into", "using", "used", "use", "our", "its",
    "their", "which", "while", "over", "than", "then", "such", "via", "per",
}


def _significant_words(text: str) -> set:
    words = re.findall(r"[a-zA-Z0-9+#.]+", (text or "").lower())
    return {w for w in words if len(w) > 2 and w not in _STOPWORDS}


def _normalize_term(term: str) -> str:
    return re.sub(r"[^a-z0-9+#.]", "", (term or "").lower().strip())


def _normalize_name(name: Optional[str]) -> str:
    return (name or "").strip().lower()


def flatten_profile_skill_terms(profile_data: Dict[str, Any]) -> set:
    """Collects the user's actual skill/technology terms from their profile for matching against a JD."""
    original = (profile_data or {}).get("original_resume", {}) or {}
    terms = set()

    for category in original.get("skills") or []:
        for skill in category.get("skills") or []:
            if skill:
                terms.add(skill.strip().lower())

    for project in original.get("projects") or []:
        for tech in project.get("technologies") or []:
            if tech:
                terms.add(tech.strip().lower())

    for cert in original.get("certifications") or []:
        if cert.get("name"):
            terms.add(cert["name"].strip().lower())

    for lang in original.get("languages") or []:
        if lang:
            terms.add(lang.strip().lower())

    terms.discard("")
    return terms


def _skill_covered(skill: str, normalized_profile_terms: set) -> bool:
    norm = _normalize_term(skill)
    if not norm:
        return False
    if norm in normalized_profile_terms:
        return True
    return any(
        (norm in term or term in norm)
        for term in normalized_profile_terms
        if len(term) >= 3
    )


def compute_skill_coverage(
    required: List[str], preferred: List[str], profile_terms: set
) -> Dict[str, Any]:
    """Deterministic set-overlap between JD-stated skills and the user's actual skill terms."""
    normalized_profile = {_normalize_term(t) for t in profile_terms}
    normalized_profile.discard("")

    required_covered = [s for s in required if _skill_covered(s, normalized_profile)]
    required_missing = [s for s in required if not _skill_covered(s, normalized_profile)]
    preferred_covered = [s for s in preferred if _skill_covered(s, normalized_profile)]
    preferred_missing = [s for s in preferred if not _skill_covered(s, normalized_profile)]

    total = len(required) + len(preferred)
    covered = len(required_covered) + len(preferred_covered)
    skill_match_pct = round((covered / total) * 100) if total else 100

    return {
        "required_skills_covered": required_covered,
        "required_skills_missing": required_missing,
        "preferred_skills_covered": preferred_covered,
        "preferred_skills_missing": preferred_missing,
        "skill_match_pct": skill_match_pct,
    }


def compute_overall_score(
    skill_match_pct: int,
    project_relevance_score: int,
    experience_relevance_score: int,
    education_match_score: int,
) -> int:
    weighted = (
        skill_match_pct * SKILL_WEIGHT
        + project_relevance_score * PROJECT_WEIGHT
        + experience_relevance_score * EXPERIENCE_WEIGHT
        + education_match_score * EDUCATION_WEIGHT
    )
    return max(0, min(100, round(weighted)))


def verify_bullet_grounding(bullet: str, original_bullets: List[str], technologies: List[str]) -> bool:
    """
    Guards against hallucinated bullets: an optimized bullet must share meaningful
    word overlap with the project's original bullets/technologies to be trusted.
    """
    bullet_words = _significant_words(bullet)
    if not bullet_words:
        return False

    source_words = set()
    for original in original_bullets:
        source_words |= _significant_words(original)
    for tech in technologies:
        source_words |= _significant_words(tech)

    if not source_words:
        return False

    overlap = bullet_words & source_words
    ratio = len(overlap) / len(bullet_words)
    return ratio >= GROUNDING_OVERLAP_RATIO or len(overlap) >= GROUNDING_MIN_OVERLAP_WORDS


def extract_optimized_projects(
    original_projects: List[Dict[str, Any]], optimized_projects: List[Project]
) -> List[OptimizedProject]:
    """
    Pairs the LLM-tailored projects back to the user's original (canonical, immutable)
    projects by name, caps bullets at MAX_BULLETS_PER_PROJECT, and verifies each
    optimized bullet is grounded in the original content — falling back to the
    original bullet at that position if it isn't.
    """
    original_by_name = {
        _normalize_name(p.get("name")): p for p in original_projects if p.get("name")
    }

    results: List[OptimizedProject] = []

    for opt_project in optimized_projects:
        original = original_by_name.get(_normalize_name(opt_project.name))
        if not original:
            # No matching canonical project to verify against — skip rather than trust blindly.
            continue

        original_bullets = list(original.get("description") or [])
        technologies = list(original.get("technologies") or opt_project.technologies or [])

        verified_bullets: List[str] = []
        for i, bullet in enumerate((opt_project.description or [])[:MAX_BULLETS_PER_PROJECT]):
            if verify_bullet_grounding(bullet, original_bullets, technologies):
                verified_bullets.append(bullet)
            elif i < len(original_bullets):
                verified_bullets.append(original_bullets[i])

        if not verified_bullets and original_bullets:
            verified_bullets = original_bullets[:MAX_BULLETS_PER_PROJECT]

        if verified_bullets:
            results.append(
                OptimizedProject(
                    project_name=original.get("name") or opt_project.name or "Untitled Project",
                    technologies=technologies,
                    original_bullets=original_bullets,
                    optimized_bullets=verified_bullets,
                )
            )

    if not results and original_projects:
        # The agent dropped every project (parsing edge case) — surface the user's
        # own top projects unmodified rather than returning nothing.
        for original in original_projects[:3]:
            bullets = list(original.get("description") or [])[:MAX_BULLETS_PER_PROJECT]
            if not bullets:
                continue
            results.append(
                OptimizedProject(
                    project_name=original.get("name") or "Untitled Project",
                    technologies=list(original.get("technologies") or []),
                    original_bullets=bullets,
                    optimized_bullets=bullets,
                )
            )

    return results


def extract_job_skill_terms(job: Dict[str, Any]) -> List[str]:
    """
    Best-effort list of the skills a job asks for. Prefers the provider's tagged
    `skills` array; when that's empty (Jooble never populates it) it mines the
    description for terms in the known skill vocabulary, so a job still gets a
    real keyword signal instead of defaulting to "no requirements".
    """
    tagged = [s for s in (job.get("skills") or []) if s and str(s).strip()]
    if tagged:
        return taxonomy.canonicalize_skills([str(s) for s in tagged])

    text = clean_html_text(job.get("description"))[:JD_SKILL_SCAN_CHARS].lower()
    if not text:
        return []

    found: List[str] = []
    seen = set()
    for canonical, aliases in taxonomy.SKILL_ALIASES.items():
        for term in (canonical, *aliases):
            normalized = term.lower().strip()
            if not normalized:
                continue
            # Word-boundary match so "go" doesn't fire on "going" and "r" can
            # never match a bare letter inside another word.
            pattern = rf"(?<![a-z0-9+#]){re.escape(normalized)}(?![a-z0-9+#])"
            if re.search(pattern, text):
                if canonical not in seen:
                    seen.add(canonical)
                    found.append(canonical)
                break
    return found


def compute_quick_ats_match(
    profile_terms: set,
    job: Dict[str, Any],
    features: Optional[Dict[str, float]] = None,
) -> int:
    """
    Deterministic 0-100 estimate of how well the user's resume matches a job,
    cheap enough to run for every card in a job list (no LLM, no network).

    Combines the same keyword-coverage logic the full ATS score uses with the
    semantic/family/seniority features the retrieval pipeline already produced.
    Reproducible for a given (profile, job) pair - the same inputs always give
    the same number.
    """
    features = features or {}
    job_skills = extract_job_skill_terms(job)

    coverage = compute_skill_coverage(job_skills, [], profile_terms)
    skill_component = coverage["skill_match_pct"] / 100.0

    if len(job_skills) < MIN_JD_SKILLS_FOR_CONFIDENCE:
        # Thin keyword evidence: blend toward neutral rather than letting one or
        # two incidental terms swing the whole score to an extreme.
        confidence = len(job_skills) / MIN_JD_SKILLS_FOR_CONFIDENCE
        skill_component = skill_component * confidence + 0.5 * (1 - confidence)

    def _feature(name: str, default: float) -> float:
        value = features.get(name, default)
        try:
            return max(0.0, min(1.0, float(value)))
        except (TypeError, ValueError):
            return default

    weighted = (
        skill_component * QUICK_SKILL_WEIGHT
        + _feature("semantic", 0.5) * QUICK_SEMANTIC_WEIGHT
        + _feature("family_fit", 0.5) * QUICK_FAMILY_WEIGHT
        + _feature("seniority_fit", 0.8) * QUICK_SENIORITY_WEIGHT
    )
    return max(0, min(100, round(weighted * 100)))


def build_job_ats_summaries(
    profile_data: Dict[str, Any],
    entries: List[Dict[str, Any]],
    cached_scores: Optional[Dict[str, Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """
    Annotates job-list entries with the ATS match percentage each card shows.

    A previously analyzed job reuses its real (LLM-backed) overall_score so the
    card and the detail view never disagree; everything else gets the quick
    deterministic estimate. `ats_score_source` tells the UI which it got, so an
    estimate can be labeled as one rather than passed off as a full analysis.

    Each entry is a dict with at least a "job" key (a job row dict) and
    optionally "feature_scores"/"features". Entries are annotated in place and
    returned for convenience.
    """
    cached_scores = cached_scores or {}
    profile_terms = flatten_profile_skill_terms(profile_data)

    for entry in entries:
        job = entry.get("job") or {}
        job_id = job.get("id")
        cached = cached_scores.get(job_id) if job_id else None
        cached_overall = (cached or {}).get("overall_score")

        if cached_overall is not None:
            entry["ats_match_score"] = _clamp_score(cached_overall)
            entry["ats_score_source"] = "analyzed"
        else:
            features = entry.get("features") or entry.get("feature_scores") or {}
            entry["ats_match_score"] = compute_quick_ats_match(profile_terms, job, features)
            entry["ats_score_source"] = "estimated"

    return entries


def _clamp_score(value: Any) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = 0
    return max(0, min(100, parsed))


async def compute_ats_score(
    profile_data: Dict[str, Any], job_title: str, job_description: str
) -> Optional[ATSScore]:
    """
    Hybrid ATS score: an LLM classifies required/preferred skills from the JD text
    and scores the qualitative fit dimensions; Python does the deterministic skill
    set-matching and combines everything into a reproducible overall score.
    """
    llm_result = await run_ats_scoring(profile_data, job_title, job_description)
    if not llm_result:
        return None

    profile_terms = flatten_profile_skill_terms(profile_data)
    required = llm_result.get("required_skills") or []
    preferred = llm_result.get("preferred_skills") or []
    coverage = compute_skill_coverage(required, preferred, profile_terms)

    project_relevance_score = _clamp_score(llm_result.get("project_relevance_score"))
    experience_relevance_score = _clamp_score(llm_result.get("experience_relevance_score"))
    education_match_score = _clamp_score(llm_result.get("education_match_score"))

    overall_score = compute_overall_score(
        coverage["skill_match_pct"],
        project_relevance_score,
        experience_relevance_score,
        education_match_score,
    )

    missing_keywords = list(
        dict.fromkeys(coverage["required_skills_missing"] + coverage["preferred_skills_missing"])
    )

    return ATSScore(
        overall_score=overall_score,
        skill_match_pct=coverage["skill_match_pct"],
        required_skills_covered=coverage["required_skills_covered"],
        required_skills_missing=coverage["required_skills_missing"],
        preferred_skills_covered=coverage["preferred_skills_covered"],
        preferred_skills_missing=coverage["preferred_skills_missing"],
        project_relevance_score=project_relevance_score,
        project_relevance_notes=llm_result.get("project_relevance_notes", ""),
        experience_relevance_score=experience_relevance_score,
        experience_relevance_notes=llm_result.get("experience_relevance_notes", ""),
        education_match_score=education_match_score,
        education_match_notes=llm_result.get("education_match_notes", ""),
        missing_keywords=missing_keywords,
        suggestions=llm_result.get("suggestions") or [],
    )
