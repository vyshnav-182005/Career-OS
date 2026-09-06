import logging

from fastapi import APIRouter, Depends, HTTPException, status

from backend.models.schemas import ProfileEditRequest, ProfileEditResult
from backend.security import verify_internal_request
from backend.services.profile_editing import ProfileNotFoundError, save_profile_edit

logger = logging.getLogger(__name__)

router = APIRouter(prefix='/resume-management', tags=['Resume Management'])


@router.put(
    "/profile/sections",
    response_model=ProfileEditResult,
    summary="Save hand-edited profile sections (certifications, publications, project bullets)",
    dependencies=[Depends(verify_internal_request)],
)
async def edit_profile_sections(payload: ProfileEditRequest) -> ProfileEditResult:
    """
    Saves the sections the user maintains by hand, without a resume upload.

    Sections left out of the request are not touched, so the editor can save
    one panel without restating the rest of the profile. A later re-parse
    merges rather than replaces these sections, so what is saved here survives
    the next resume upload.
    """
    try:
        return save_profile_edit(payload)
    except ProfileNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.exception("Profile edit failed for user_id=%s", payload.user_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Could not save profile changes: {e}",
        )
