import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status

from backend.models.schemas import GithubSyncRequest, GithubSyncResult
from backend.security import verify_internal_request
from backend.services.github_enrichment import (
    enrich_github_project_descriptions,
    sync_github_projects,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix='/user-profile', tags=['User Profile'])


@router.post(
    "/github/sync",
    response_model=GithubSyncResult,
    summary="Re-scan the linked GitHub account and reconcile the project list",
    dependencies=[Depends(verify_internal_request)],
)
async def sync_github(
    payload: GithubSyncRequest, background_tasks: BackgroundTasks
) -> GithubSyncResult:
    """
    Brings the profile's projects back in line with the GitHub account: new
    repos appear, deleted ones are removed, renames follow the repo.

    The reconcile itself is fast and answers immediately. Rewriting the repo
    blurbs into real resume bullets needs a README read per repo plus an LLM
    call, so it is queued to run after the response and updates the profile
    when it lands -- the same shape as the enrichment that follows a resume
    upload.

    A failed sync answers 200 with success=false and an explanation, because
    "GitHub is unreachable right now" is a normal outcome for a button the user
    can press at any time, not a fault in the request. The only 500 is a bug.
    """
    try:
        result = await sync_github_projects(payload.user_id)
    except Exception as e:
        logger.exception("GitHub sync failed for user_id=%s", payload.user_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"GitHub sync failed: {e}",
        )

    if result.success:
        background_tasks.add_task(enrich_github_project_descriptions, payload.user_id)

    return result
