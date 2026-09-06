import logging
from typing import Optional

from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

# NOTE: torch is deliberately left on its default thread count here. Capping it
# to free cores for the request path was tried and measured backwards: at 4
# threads a 64-job batch took 3.05s against 1.19s at 20 (19ms -> 48ms per job),
# so ingestion simply contended for 2.6x as long. The pressure ingestion puts on
# a request is dominated by how long a run lasts, not how many cores it uses
# while it lasts - so it is paced and serialised in routers/jobs.py instead.

# Load the model lazily so we don't block app startup unless we need it
_model = None

def get_model():
    global _model
    if _model is None:
        logger.info("Loading sentence-transformer model (all-MiniLM-L6-v2)...")
        _model = SentenceTransformer('all-MiniLM-L6-v2')
    return _model

def build_job_embedding_text(title: str, description: str, skills: list[str]) -> str:
    """Concatenates a job's key fields into one rich semantic representation."""
    skills_str = ", ".join(skills) if skills else "No specific skills"
    return f"Title: {title}\nSkills: {skills_str}\nDescription: {description or ''}"


def generate_job_embedding(title: str, description: str, skills: list[str]) -> list[float]:
    """
    Generates a 384-dimensional vector embedding for a job.
    Combines the title, skills, and description.
    """
    try:
        model = get_model()
        # output is a numpy array, we convert to list of floats for pgvector/Supabase
        embedding = model.encode(build_job_embedding_text(title, description, skills))
        return embedding.tolist()
    except Exception as e:
        logger.exception("Failed to generate embedding")
        # Return None so callers can exclude the field from DB payloads
        return None


# Jobs per model.encode() call during ingestion. The transformer batches a list
# far more efficiently than it handles the same texts one at a time, and a
# provider fan-out routinely has hundreds of jobs to embed - which used to be
# hundreds of separate encodes, each saturating every core for ~39ms while a
# user's search waited behind it for CPU.
EMBEDDING_BATCH_SIZE = 64


def generate_job_embeddings(
    jobs: list[tuple[str, str, list[str]]]
) -> list[Optional[list[float]]]:
    """
    Batch form of generate_job_embedding: takes (title, description, skills)
    tuples and returns one embedding per input, positionally aligned, with None
    wherever the encode failed.

    A failure is contained to its own batch rather than the whole run, so one
    bad job doesn't cost the embeddings of everything ingested alongside it.
    """
    if not jobs:
        return []

    try:
        model = get_model()
    except Exception:
        logger.exception("Failed to load embedding model for %d jobs", len(jobs))
        return [None] * len(jobs)

    results: list[Optional[list[float]]] = []
    for start in range(0, len(jobs), EMBEDDING_BATCH_SIZE):
        batch = jobs[start:start + EMBEDDING_BATCH_SIZE]
        texts = [build_job_embedding_text(*job) for job in batch]
        try:
            encoded = model.encode(texts)
            results.extend(vector.tolist() for vector in encoded)
        except Exception:
            logger.exception(
                "Failed to generate embeddings for batch %d-%d of %d",
                start + 1, start + len(batch), len(jobs),
            )
            results.extend([None] * len(batch))

    return results


# all-MiniLM-L6-v2 truncates at 256 word-pieces; cap well under that so
# whole-word splitting (word-pieces can split a single word further) doesn't
# silently lose the tail of the text.
PROFILE_EMBEDDING_MAX_WORDS = 200


def _dedupe_preserve_order(items: list[str]) -> list[str]:
    seen = set()
    result = []
    for item in items:
        cleaned = (item or "").strip()
        key = cleaned.lower()
        if cleaned and key not in seen:
            seen.add(key)
            result.append(cleaned)
    return result


def build_profile_embedding_text(profile_data: dict) -> str:
    """
    Builds the text to embed for a profile. Mirrors the job-side
    "Title: ... Skills: ... Description: ..." shape so both vectors land in
    the same region of embedding space. Title/skills are written first so
    they survive truncation; the description (strengths + summary) is least
    critical and goes last.
    """
    original = profile_data.get("original_resume") or {}
    roles = profile_data.get("preferred_job_roles") or []
    strengths = profile_data.get("strengths") or []
    personal_info = original.get("personal_info") or {}

    role_titles = [r.get("title", "") for r in roles if isinstance(r, dict) and r.get("title")]
    experience_titles = [
        e.get("title", "") for e in (original.get("experience") or []) if isinstance(e, dict) and e.get("title")
    ]
    title_str = ", ".join(_dedupe_preserve_order(role_titles + experience_titles)) or "Not specified"

    flat_skills = [
        skill for category in (original.get("skills") or []) if isinstance(category, dict)
        for skill in (category.get("skills") or [])
    ]
    project_technologies = [
        tech for project in (original.get("projects") or []) if isinstance(project, dict)
        for tech in (project.get("technologies") or [])
    ]
    skills_str = ", ".join(_dedupe_preserve_order(flat_skills + project_technologies)) or "No specific skills"

    summary = personal_info.get("summary") or ""
    description_parts = []
    if strengths:
        description_parts.append(", ".join(strengths))
    if summary:
        description_parts.append(summary)
    description_str = " ".join(description_parts) or "No summary available"

    text_to_embed = f"Title: {title_str}\nSkills: {skills_str}\nDescription: {description_str}"

    words = text_to_embed.split()
    if len(words) > PROFILE_EMBEDDING_MAX_WORDS:
        text_to_embed = " ".join(words[:PROFILE_EMBEDDING_MAX_WORDS])

    return text_to_embed


def generate_profile_embedding(profile_data: dict) -> list[float]:
    """
    Generates a 384-dimensional vector embedding for a user profile.
    Combines preferred roles/experience titles, skills, and strengths/summary.
    """
    try:
        model = get_model()

        text_to_embed = build_profile_embedding_text(profile_data)

        embedding = model.encode(text_to_embed)
        return embedding.tolist()
    except Exception as e:
        logger.exception("Failed to generate profile embedding")
        return []
