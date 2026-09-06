import logging

from fastapi import APIRouter, Depends, HTTPException, status

from backend.models.schemas import GithubSyncRequest, GithubSyncResult
from backend.security import verify_internal_request
from backend.services.github_enrichment import sync_github_projects

logger = logging.getLogger(__name__)

router = APIRouter(prefix='/user-profile', tags=['User Profile'])


@router.post(
    "/github/sync",
    response_model=GithubSyncResult,
    summary="Re-scan the linked GitHub account and reconcile the project list",
    dependencies=[Depends(verify_internal_request)],
)
async def sync_github(payload: GithubSyncRequest) -> GithubSyncResult:
    """
    Brings the profile's projects back in line with the GitHub account: new
    repos appear, deleted ones are removed, renames follow the repo.

    A failed sync answers 200 with success=false and an explanation, because
    "GitHub is unreachable right now" is a normal outcome for a button the user
    can press at any time, not a fault in the request. The only 500 is a bug.
    """
    try:
        return await sync_github_projects(payload.user_id)
    except Exception as e:
        logger.exception("GitHub sync failed for user_id=%s", payload.user_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"GitHub sync failed: {e}",
        )
