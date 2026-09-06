import ast
import json
import re
from pydantic import BaseModel, Field, field_validator
from typing import Any, Literal, Optional


# Leading bullet glyphs / list markers on a line that is already going to be
# rendered inside an <li>.
_LEADING_MARKER_RE = re.compile(r"^\s*(?:[-*+•‣▪●◦⁃∙·]|\d{1,2}[.)])\s+")
# Wrapping quotes/brackets left behind by a stringified list element.
_WRAPPING_JUNK_RE = re.compile(r"^[\s\[\]'\"`]+|[\s\[\]'\"`]+$")


def _looks_like_encoded_list(text: str) -> bool:
    stripped = text.strip()
    return (stripped.startswith("[") and stripped.endswith("]")) or (
        stripped.startswith("{") and stripped.endswith("}")
    )


def _decode_encoded_list(text: str) -> Optional[list]:
    """
    Recovers a real list from a model that returned its bullets as one string
    containing list syntax — "['Did X', 'Did Y']" — instead of a JSON array.
    Tries JSON first, then Python literal syntax (single quotes).
    """
    stripped = text.strip()
    for parser in (json.loads, ast.literal_eval):
        try:
            parsed = parser(stripped)
        except Exception:
            continue
        if isinstance(parsed, list):
            return parsed
        if isinstance(parsed, dict):
            return list(parsed.values())
    return None


def _clean_bullet(text: str) -> str:
    """Strips list syntax, stray quotes and leading bullet glyphs off one bullet."""
    cleaned = str(text).strip()
    cleaned = _WRAPPING_JUNK_RE.sub("", cleaned)
    cleaned = _LEADING_MARKER_RE.sub("", cleaned)
    # A trailing comma is the giveaway of a split-up list literal.
    cleaned = cleaned.rstrip(",").strip()
    return " ".join(cleaned.split())


def normalize_bullets(value: Any) -> list[str]:
    """
    Coerces whatever an agent returned for a bullet field into a clean list of
    individual bullet strings.

    LLMs regularly return these fields as a single string holding a stringified
    array ("['Built X', 'Shipped Y']"), a newline-joined blob, or a list with
    one such string inside it — all of which used to reach the resume template
    verbatim and render as literal "[ ... ]" text in the PDF. Normalizing on the
    model means every entry point (resume parsing, LLM optimization, cached
    snapshots loaded back from the DB) is covered by construction.
    """
    if value is None:
        return []

    if isinstance(value, str):
        items: list = [value]
    elif isinstance(value, (list, tuple)):
        items = list(value)
    elif isinstance(value, dict):
        items = list(value.values())
    else:
        items = [value]

    bullets: list[str] = []
    for item in items:
        if item is None:
            continue
        if isinstance(item, (list, tuple)):
            bullets.extend(normalize_bullets(list(item)))
            continue
        if isinstance(item, dict):
            bullets.extend(normalize_bullets(list(item.values())))
            continue

        text = str(item).strip()
        if not text:
            continue

        if _looks_like_encoded_list(text):
            decoded = _decode_encoded_list(text)
            if decoded is not None:
                bullets.extend(normalize_bullets(decoded))
                continue

        # A multi-line blob is really several bullets sharing one string.
        if "\n" in text:
            for line in text.split("\n"):
                cleaned = _clean_bullet(line)
                if cleaned:
                    bullets.append(cleaned)
            continue

        cleaned = _clean_bullet(text)
        if cleaned:
            bullets.append(cleaned)

    # De-duplicate while preserving order: a repeated bullet only wastes space.
    seen: set[str] = set()
    unique: list[str] = []
    for bullet in bullets:
        key = bullet.lower()
        if key not in seen:
            seen.add(key)
            unique.append(bullet)
    return unique


def _normalize_terms(value: Any) -> list[str]:
    """
    Like normalize_bullets, but for short comma-separated term lists (skills,
    technologies, languages) which models often return as one joined string.
    """
    bullets = normalize_bullets(value)
    if len(bullets) == 1 and "," in bullets[0]:
        return [part.strip() for part in bullets[0].split(",") if part.strip()]
    return bullets


class PersonalInfo(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    location: Optional[str] = None
    linkedin: Optional[str] = None
    github: Optional[str] = None
    website: Optional[str] = None
    summary: Optional[str] = None


class Education(BaseModel):
    institution: Optional[str] = None
    degree: Optional[str] = None
    field_of_study: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    gpa: Optional[str] = None
    description: Optional[str] = None


class Experience(BaseModel):
    company: Optional[str] = None
    title: Optional[str] = None
    location: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    is_current: bool = False
    responsibilities: list[str] = Field(default_factory=list)

    @field_validator("responsibilities", mode="before")
    @classmethod
    def _normalize_responsibilities(cls, value: Any) -> list[str]:
        return normalize_bullets(value)


class Project(BaseModel):
    name: Optional[str] = None
    description: list[str] = Field(default_factory=list)
    technologies: list[str] = Field(default_factory=list)
    url: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None

    # Structured raw material for per-JD tailoring, kept separate from
    # `description` (which stays the "as last phrased" bullet list actually
    # rendered on the resume). These hold the underlying facts once, so a
    # tailoring pass can re-phrase them for a given JD without having to
    # reverse-engineer them back out of prose. All optional, so projects
    # stored before these existed validate unchanged.
    role: Optional[str] = None
    approach: Optional[str] = None
    impact: Optional[str] = None
    scale: Optional[str] = None

    # Who wrote the current `description`: the user by hand, or a generator
    # (the resume-optimization agent, or the GitHub-scan enrichment). None
    # means the project predates this field; treat it as "user" so we never
    # auto-overwrite text whose origin we don't actually know.
    description_source: Optional[Literal["user", "ai_generated"]] = None

    # Only `description` is bullet-normalized. role/approach/impact/scale are
    # free-form single strings, deliberately left untouched by this validator.
    @field_validator("description", mode="before")
    @classmethod
    def _normalize_description(cls, value: Any) -> list[str]:
        return normalize_bullets(value)

    @field_validator("technologies", mode="before")
    @classmethod
    def _normalize_technologies(cls, value: Any) -> list[str]:
        return _normalize_terms(value)


class Certification(BaseModel):
    name: Optional[str] = None
    issuer: Optional[str] = None
    date: Optional[str] = None
    expiry: Optional[str] = None
    credential_id: Optional[str] = None


class SkillCategory(BaseModel):
    category: Optional[str] = None
    skills: list[str] = Field(default_factory=list)

    @field_validator("skills", mode="before")
    @classmethod
    def _normalize_skills(cls, value: Any) -> list[str]:
        return _normalize_terms(value)


class Publication(BaseModel):
    title: Optional[str] = None
    publisher: Optional[str] = None
    date: Optional[str] = None
    url: Optional[str] = None
    description: Optional[str] = None


class CustomSectionItem(BaseModel):
    title: Optional[str] = None
    subtitle: Optional[str] = None
    date: Optional[str] = None
    description: Optional[str] = None


class CustomSection(BaseModel):
    section_title: str
    items: list[CustomSectionItem] = Field(default_factory=list)


class ParsedResume(BaseModel):
    personal_info: Optional[PersonalInfo] = None
    education: list[Education] = Field(default_factory=list)
    experience: list[Experience] = Field(default_factory=list)
    projects: list[Project] = Field(default_factory=list)
    certifications: list[Certification] = Field(default_factory=list)
    skills: list[SkillCategory] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    publications: list[Publication] = Field(default_factory=list)
    custom_sections: list[CustomSection] = Field(default_factory=list)
    raw_text: Optional[str] = None

    @field_validator("languages", mode="before")
    @classmethod
    def _normalize_languages(cls, value: Any) -> list[str]:
        return _normalize_terms(value)


class ParseResponse(BaseModel):
    success: bool
    data: Optional[ParsedResume] = None
    error: Optional[str] = None
    filename: Optional[str] = None
    file_type: Optional[str] = None
