import logging
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

# Load the model lazily so we don't block app startup unless we need it
_model = None

def get_model():
    global _model
    if _model is None:
        logger.info("Loading sentence-transformer model (all-MiniLM-L6-v2)...")
        _model = SentenceTransformer('all-MiniLM-L6-v2')
    return _model

def generate_job_embedding(title: str, description: str, skills: list[str]) -> list[float]:
    """
    Generates a 384-dimensional vector embedding for a job.
    Combines the title, skills, and description.
    """
    try:
        model = get_model()
        
        # We concatenate key fields to create a rich semantic representation
        skills_str = ", ".join(skills) if skills else "No specific skills"
        text_to_embed = f"Title: {title}\nSkills: {skills_str}\nDescription: {description or ''}"
        
        # Generate embedding
        # output is a numpy array, we convert to list of floats for pgvector/Supabase
        embedding = model.encode(text_to_embed)
        return embedding.tolist()
    except Exception as e:
        logger.exception("Failed to generate embedding")
        # Return None so callers can exclude the field from DB payloads
        return None

def generate_profile_embedding(profile_data: dict) -> list[float]:
    """
    Generates a 384-dimensional vector embedding for a user profile.
    Combines strengths, preferred roles, and original resume summary.
    """
    try:
        model = get_model()
        
        strengths = profile_data.get("strengths", [])
        roles = profile_data.get("preferred_job_roles", [])
        original = profile_data.get("original_resume", {})
        
        strengths_str = ", ".join(strengths) if strengths else "None specified"
        roles_str = ", ".join([r.get("title", "") for r in roles if isinstance(r, dict)]) if roles else "None specified"
        summary = original.get("summary", "")
        
        text_to_embed = f"Profile Strengths: {strengths_str}\nPreferred Roles: {roles_str}\nSummary: {summary}"
        
        embedding = model.encode(text_to_embed)
        return embedding.tolist()
    except Exception as e:
        logger.exception("Failed to generate profile embedding")
        return []
