import logging
from fastapi import UploadFile, BackgroundTasks
from typing import Tuple, Any

from services.resume_parsing.parser import parse_resume
from services.resume_parsing.supabase_client import upsert_parsed_resume
from services.resume_parsing.agent import run_profile_intelligence
from services.config import settings

logger = logging.getLogger(__name__)

ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/msword",
}

async def parse_resume_service(user_id: str, file: UploadFile, background_tasks: BackgroundTasks) -> Tuple[Any, str, str]:
    content_type = file.content_type or ""
    filename = file.filename or ""

    if content_type not in ALLOWED_CONTENT_TYPES:
        if filename.lower().endswith(".pdf"):
            content_type = "application/pdf"
        elif filename.lower().endswith(".docx"):
            content_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        else:
            raise ValueError(f"Unsupported file type '{content_type}'. Please upload a PDF or DOCX file.")

    file_bytes = await file.read()

    max_bytes = settings.max_file_size_mb * 1024 * 1024
    if len(file_bytes) > max_bytes:
        raise ValueError(f"File exceeds maximum size of {settings.max_file_size_mb} MB.")

    if not file_bytes:
        raise ValueError("Uploaded file is empty.")

    # Call the original parser function
    parsed = parse_resume(file_bytes, content_type)
    
    # Upload to Supabase and update profiles table with initial data
    upsert_parsed_resume(user_id, parsed, file_bytes, content_type, filename)
    
    # Trigger the profile intelligence agent in the background
    background_tasks.add_task(run_profile_intelligence, user_id)
    
    return parsed, filename, content_type
