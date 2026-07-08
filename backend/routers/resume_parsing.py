from fastapi import APIRouter, File, UploadFile, HTTPException, status, Form, BackgroundTasks
from pydantic import BaseModel
from typing import Any, Optional
import logging

from backend.services.resume_parser import parse_resume_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix='/resume-parsing', tags=['Resume Parsing'])

class ParseResponse(BaseModel):
    success: bool
    data: Any
    filename: Optional[str] = None
    file_type: Optional[str] = None

@router.post("/parse", response_model=ParseResponse, summary="Parse a resume file")
async def parse_resume_endpoint(
    background_tasks: BackgroundTasks,
    user_id: str = Form(...),
    file: UploadFile = File(...)
):
    """
    Accept a resume file upload and return structured JSON.
    """
    try:
        parsed_data, filename, content_type = await parse_resume_service(user_id, file, background_tasks)
        return ParseResponse(
            success=True,
            data=parsed_data,
            filename=filename,
            file_type=content_type,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except Exception as e:
        logger.exception("Unexpected error in parse_resume_endpoint: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred while parsing the resume: {e}"
        )
