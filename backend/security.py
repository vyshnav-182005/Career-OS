import logging

from fastapi import Header, HTTPException, status

from backend.config import settings

logger = logging.getLogger(__name__)


async def verify_internal_request(x_internal_secret: str = Header(default="")) -> None:
    """
    Guards endpoints that accept a user_id and must only be reachable through the
    Next.js server (which has already verified the caller's session), not directly
    from a browser that could pass an arbitrary user_id.
    """
    if not settings.internal_api_secret or x_internal_secret != settings.internal_api_secret:
        logger.warning("Rejected request missing/invalid X-Internal-Secret header")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")