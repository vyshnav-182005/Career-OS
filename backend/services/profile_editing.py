"""Applies one save from the profile editor to the stored profile.

Reads the profile, folds in only the sections the request carried, and writes
it back. Kept apart from profile_sections.py so the merge rules there stay
free of database access and can be tested as plain data.
"""

import logging

from backend.db.supabase_client import get_profile_data, save_profile_data
from backend.models.schemas import ProfileEditRequest, ProfileEditResult
from backend.services.profile_sections import apply_project_description_edits

logger = logging.getLogger(__name__)


class ProfileNotFoundError(Exception):
    """Raised when there is no parsed profile to edit yet."""


def _describe(counts: dict[str, int]) -> str:
    parts = [f"{value} {label}" for label, value in counts.items() if value]
    if not parts:
        # Reached when a section was replaced with an empty one -- the user
        # removed their last entry, which is a real save with nothing to count.
        return "Changes saved."
    return "Saved " + ", ".join(parts) + "."


def save_profile_edit(request: ProfileEditRequest) -> ProfileEditResult:
    """Writes the edited sections onto the stored profile.

    A section the request left out is not touched: the editor saves one panel
    at a time, and an absent field must never read as "the user emptied this".
    """
    profile_data = get_profile_data(request.user_id)
    if not profile_data or "original_resume" not in profile_data:
        raise ProfileNotFoundError(
            "There is no profile to edit yet. Upload a resume first."
        )

    resume = profile_data["original_resume"]
    counts = {"certifications": 0, "publications": 0, "projects": 0}
    unmatched: list[str] = []
    # Tracked apart from the counts because emptying a section is a save with
    # nothing to count: "0 certifications" is exactly what removing the last
    # one looks like, and reading that as "nothing changed" would drop it.
    touched = False

    # The editor renders the whole list and sends it back, so these two are a
    # replace rather than a merge -- a removed entry has to actually go.
    if request.certifications is not None:
        resume["certifications"] = [c.model_dump() for c in request.certifications]
        counts["certifications"] = len(request.certifications)
        touched = True

    if request.publications is not None:
        resume["publications"] = [p.model_dump() for p in request.publications]
        counts["publications"] = len(request.publications)
        touched = True

    if request.project_descriptions:
        counts["projects"], unmatched = apply_project_description_edits(
            resume.get("projects") or [], request.project_descriptions
        )
        # Unlike the lists above, a description edit that matches what is
        # already stored is genuinely a no-op -- see apply_project_description_edits.
        touched = touched or counts["projects"] > 0

    if not touched:
        return ProfileEditResult(
            success=True, message="No changes to save.", unmatched_projects=unmatched
        )

    if not save_profile_data(request.user_id, profile_data):
        return ProfileEditResult(
            success=False, message="Could not save your changes. Please try again."
        )

    logger.info("Profile edit saved for user_id=%s: %s", request.user_id, counts)

    return ProfileEditResult(
        success=True,
        message=_describe(counts),
        certifications=counts["certifications"],
        publications=counts["publications"],
        projects_updated=counts["projects"],
        unmatched_projects=unmatched,
    )
