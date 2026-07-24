"""
Resume Parser — Core extraction and profile intelligence logic.

Pipeline:
  1. Extract raw text from PDF (PyMuPDF) or DOCX (python-docx)
  2. Send text to NVIDIA NIM (Llama 3.1 70B) with a unified prompt to extract
     the parsed resume AND generate profile intelligence in a single pass.
  3. Parse the JSON response into a ProfileIntelligence model.
"""

import json
import logging
import re
import tempfile
from pathlib import Path
from typing import Tuple, Any
from fastapi import UploadFile, BackgroundTasks

import fitz  # PyMuPDF
from openai import OpenAI
from docx import Document

from backend.config import settings
from backend.models.resume import ParsedResume
from backend.db.supabase_client import upsert_parsed_resume
from backend.services.workflow_orchestrator import trigger_profile_intelligence_workflow

logger = logging.getLogger(__name__)

PARSE_RESUME_PROMPT = """
You are an expert resume parser. Your task is to analyze the raw text of a resume and extract all structured data.

Return a JSON object matching this EXACT schema (no extra keys, no markdown, no explanatory text):

{{
  "personal_info": {{
    "name": "string or null",
    "email": "string or null",
    "phone": "string or null",
    "location": "string or null",
    "linkedin": "string or null",
    "github": "string or null",
    "website": "string or null",
    "summary": "string or null"
  }},
  "education": [
    {{
      "institution": "string",
      "degree": "string or null",
      "field_of_study": "string or null",
      "start_date": "string or null",
      "end_date": "string or null",
      "gpa": "string or null",
      "description": "string or null"
    }}
  ],
  "experience": [
    {{
      "company": "string",
      "title": "string",
      "location": "string or null",
      "start_date": "string or null",
      "end_date": "string or null",
      "is_current": false,
      "responsibilities": ["string (split bullet points into separate strings exactly as they appear in the resume. DO NOT summarize or omit any data)"]
    }}
  ] (or null if no explicit work experience exists),
  "projects": [
    {{
      "name": "string",
      "description": ["string (split bullet points into separate strings exactly as they appear in the resume. DO NOT summarize or omit any data)"],
      "technologies": ["string"],
      "url": "string or null",
      "start_date": "string or null",
      "end_date": "string or null"
    }}
  ],
  "certifications": [
    {{
      "name": "string",
      "issuer": "string or null",
      "date": "string or null",
      "expiry": "string or null",
      "credential_id": "string or null"
    }}
  ],
  "skills": [
    {{
      "category": "string",
      "skills": ["string"]
    }}
  ],
  "languages": ["string"],
  "publications": [
    {{
      "title": "string",
      "publisher": "string or null",
      "date": "string or null",
      "url": "string or null",
      "description": "string or null"
    }}
  ],
  "custom_sections": [
    {{
      "section_title": "string (e.g., 'Awards', 'Volunteer Work', 'Patents')",
      "items": [
        {{
          "title": "string or null",
          "subtitle": "string or null",
          "date": "string or null",
          "description": "string or null"
        }}
      ]
    }}
  ]
}}

Rules:
1. Return ONLY valid JSON. No markdown, no code fences, no explanatory text.
2. Link Extraction (CRITICAL): You MUST aggressively search the resume for a LinkedIn profile link and place it ONLY in the `linkedin` field. Carefully distinguish between LinkedIn and GitHub URLs. LinkedIn URLs always contain 'linkedin.com', GitHub URLs always contain 'github.com'. DO NOT SWAP THEM.
3. If a field is missing, use null for scalars or [] for arrays. For experience, split bullet points into separate strings in the responsibilities array.
4. Experience vs Projects: The `experience` section MUST ONLY contain real work experience or internships EXPLICITLY MENTIONED in the resume text. Do NOT assume, infer, or hallucinate any work experience. If there is no genuine work experience explicitly mentioned in the resume text, you MUST keep the `experience` field null. All projects MUST be placed in the `projects` section without duplication.
5. Custom Sections: If the resume contains ANY sections that do not fit into the standard predefined arrays (e.g., Awards, Extracurriculars, Leadership, Hobbies), you MUST extract them into the `custom_sections` array. Do not lose any information.

Resume text:
---
{resume_text}
---
"""

def extract_text_from_pdf(file_bytes: bytes) -> str:
    """Extract raw text from PDF bytes using PyMuPDF."""
    with fitz.open(stream=file_bytes, filetype="pdf") as doc:
        pages_text = []
        for page in doc:
            pages_text.append(page.get_text("text"))
        return "\n".join(pages_text)


def extract_text_from_docx(file_bytes: bytes) -> str:
    """Extract raw text from DOCX bytes using python-docx."""
    with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp:
        tmp.write(file_bytes)
        tmp_path = Path(tmp.name)

    try:
        doc = Document(str(tmp_path))
        paragraphs = [para.text for para in doc.paragraphs if para.text.strip()]
        return "\n".join(paragraphs)
    finally:
        tmp_path.unlink(missing_ok=True)


def _clean_json_response(response_text: str) -> str:
    """Strip markdown fences if the model wraps the JSON in them."""
    cleaned = re.sub(r"^```(?:json)?\s*", "", response_text.strip(), flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned.strip())
    return cleaned.strip()


def parse_resume(file_bytes: bytes, content_type: str) -> ParsedResume:
    """
    Extracts raw text from the resume and parses it into structured data using an LLM.
    """
    # 1. Extract raw text
    if content_type == "application/pdf":
        raw_text = extract_text_from_pdf(file_bytes)
    elif content_type in (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/msword",
    ):
        raw_text = extract_text_from_docx(file_bytes)
    else:
        raise ValueError(f"Unsupported file type: {content_type}. Only PDF and DOCX are supported.")

    if not raw_text.strip():
        raise ValueError("Could not extract any text from the uploaded file.")

    logger.info("Extracted %d characters from resume", len(raw_text))

    # 2. Call NVIDIA NIM (OpenAI-compatible API) with parse resume prompt
    client = OpenAI(
        base_url="https://integrate.api.nvidia.com/v1",
        api_key=settings.nvidia_api_key,
        timeout=120.0,
        max_retries=1,
    )

    prompt = PARSE_RESUME_PROMPT.format(resume_text=raw_text[:12000])

    completion = client.chat.completions.create(
        model=settings.model,
        messages=[
            {
                "role": "system",
                "content": "You are an expert resume parser. Always respond with valid JSON only, no markdown or explanatory text.",
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.1,
        max_tokens=4096,
        response_format={"type": "json_object"},
    )

    response_text = completion.choices[0].message.content or ""
    logger.info("Received profile analysis response (%d chars)", len(response_text))

    # 3. Parse JSON
    cleaned = _clean_json_response(response_text)
    data = json.loads(cleaned)
    
    data["raw_text"] = raw_text
    
    if data.get("experience") is None:
        data["experience"] = []
        
    parsed = ParsedResume(**data)
    
    logger.info("Resume parsing complete")

    return parsed

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
    background_tasks.add_task(trigger_profile_intelligence_workflow, user_id)
    
    return parsed, filename, content_type
