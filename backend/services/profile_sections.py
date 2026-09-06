"""Profile sections the user maintains by hand, independent of resume upload.

Certifications and publications are the two sections a person keeps adding to
between resume uploads - a course finished last week is not in the PDF parsed
last month. They are therefore editable in the profile editor, which makes a
re-parse dangerous: `original_resume` used to be replaced wholesale on every
upload, so anything added by hand vanished the next time a resume was parsed.
`merge_reparsed_sections` is what stops that, and is the one piece of this
module where getting it wrong loses data rather than just annoying someone.

Project descriptions are edited here too, because that edit is what stamps
`description_source = "user"` - the label the GitHub enrichment and the merge
both refuse to write over.
"""

import logging
from typing import Any, Optional

from backend.models.resume import normalize_bullets

logger = logging.getLogger(__name__)


def _norm(value: Optional[str]) -> str:
    """Collapses a heading to a comparable key: case, spacing and padding."""
    return " ".join((value or "").lower().split())


def _certification_key(cert: dict) -> tuple:
    return _norm(cert.get("name")), _norm(cert.get("issuer"))


def _publication_key(pub: dict) -> tuple:
    return _norm(pub.get("title")), _norm(pub.get("publisher"))


def _merge_entries(existing: list, parsed: list, key_of) -> list:
    """Existing entries first and unchanged, then whatever the parse adds.

    A stored entry wins over its re-parsed twin field by field, so an issuer or
    date the user corrected by hand survives another upload of the resume that
    got it wrong; blank fields are still filled in from the parse, so a fuller
    resume entry does add what it knows. Entries the parse found and the
    profile has never seen are appended in the order the resume listed them.
    """
    merged: list = []
    index: dict[tuple, dict] = {}

    for entry in existing or []:
        if not isinstance(entry, dict):
            continue
        entry = dict(entry)
        merged.append(entry)
        index.setdefault(key_of(entry), entry)

    for entry in parsed or []:
        if not isinstance(entry, dict):
            continue
        match = index.get(key_of(entry))
        if match is None:
            entry = dict(entry)
            merged.append(entry)
            index.setdefault(key_of(entry), entry)
            continue
        for field, value in entry.items():
            if value not in (None, "", []) and match.get(field) in (None, "", []):
                match[field] = value

    return merged


def merge_reparsed_sections(existing_resume: dict, parsed_resume: dict) -> dict:
    """Folds a freshly parsed resume onto the stored one for hand-kept sections.

    Returns the parsed resume - everything a resume states is still taken from
    the new file - with certifications and publications merged rather than
    replaced, matched on name+issuer and title+publisher respectively. Without
    this, a certification typed into the editor is silently gone the next time
    the user uploads a resume that predates it.
    """
    merged = dict(parsed_resume or {})
    existing = existing_resume or {}

    merged["certifications"] = _merge_entries(
        existing.get("certifications"), merged.get("certifications"), _certification_key
    )
    merged["publications"] = _merge_entries(
        existing.get("publications"), merged.get("publications"), _publication_key
    )
    return merged


def _project_matches(project: dict, name: str, url: Optional[str]) -> bool:
    """A project is the one being edited if its link or its name says so."""
    project_url = (project.get("url") or "").strip().rstrip("/")
    edited_url = (url or "").strip().rstrip("/")
    if project_url and edited_url:
        return project_url.lower() == edited_url.lower()
    return _norm(project.get("name")) == _norm(name)


def apply_project_description_edits(
    projects: list[dict], edits: list[Any]
) -> tuple[int, list[str]]:
    """Writes edited bullets onto their projects, labelled as the user's.

    Only a description that actually differs from what is stored is stamped
    `description_source = "user"`: saving a project modal without touching the
    text must not freeze generated bullets under the user's name, which would
    stop the GitHub enrichment from ever refreshing them.

    Returns (how many projects changed, names that matched nothing).
    """
    updated = 0
    unmatched: list[str] = []

    for edit in edits or []:
        description = normalize_bullets(edit.description)
        match = next(
            (p for p in projects if isinstance(p, dict) and _project_matches(p, edit.name, edit.url)),
            None,
        )
        if match is None:
            unmatched.append(edit.name)
            continue
        if description == (match.get("description") or []):
            continue

        match["description"] = description
        match["description_source"] = "user"
        updated += 1

    if unmatched:
        logger.info("Project description edits matched no stored project: %s", unmatched)

    return updated, unmatched
