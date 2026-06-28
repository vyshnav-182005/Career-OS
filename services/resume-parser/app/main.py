"""
CareerOS — Resume Parsing Service
FastAPI microservice that accepts resume file uploads (PDF/DOCX)
and returns structured JSON via NVIDIA NIM extraction.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.models import ParseResponse, ParsedResume
from app.parser import parse_resume

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

settings = get_settings()

ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/msword",
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 CareerOS Resume Parser starting up…")
    yield
    logger.info("🛑 CareerOS Resume Parser shutting down…")


app = FastAPI(
    title="CareerOS Resume Parser",
    description="Extracts structured information from PDF/DOCX resumes using Google Gemini.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["System"])
async def health_check():
    """Health check endpoint."""
    return {"status": "ok", "service": "resume-parser", "version": "1.0.0"}


@app.post(
    "/parse",
    response_model=ParseResponse,
    tags=["Resume"],
    summary="Parse a resume file",
    description="Upload a PDF or DOCX resume and receive structured JSON with education, experience, skills, and more.",
)
async def parse_resume_endpoint(file: UploadFile = File(...)):
    """
    Accept a resume file upload and return structured JSON.

    - **file**: PDF or DOCX resume file (max 10 MB)
    """
    # Validate content type
    content_type = file.content_type or ""
    if content_type not in ALLOWED_CONTENT_TYPES:
        # Fallback: check extension
        filename = file.filename or ""
        if filename.lower().endswith(".pdf"):
            content_type = "application/pdf"
        elif filename.lower().endswith(".docx"):
            content_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        else:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail=f"Unsupported file type '{content_type}'. Please upload a PDF or DOCX file.",
            )

    # Read file bytes
    file_bytes = await file.read()

    # Enforce size limit
    max_bytes = settings.max_file_size_mb * 1024 * 1024
    if len(file_bytes) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds maximum size of {settings.max_file_size_mb} MB.",
        )

    if not file_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty.",
        )

    try:
        parsed = parse_resume(file_bytes, content_type)
        return ParseResponse(
            success=True,
            data=parsed,
            filename=file.filename,
            file_type=content_type,
        )
    except ValueError as e:
        logger.warning("Validation error parsing resume: %s", e)
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except Exception as e:
        logger.exception("Unexpected error parsing resume: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while parsing the resume. Please try again.",
        )
