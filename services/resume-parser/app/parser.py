"""
Resume Parser — Core extraction logic.

Pipeline:
  1. Extract raw text from PDF (PyMuPDF) or DOCX (python-docx)
  2. Send text to NVIDIA NIM (OpenAI-compatible API) with a structured extraction prompt
  3. Parse the JSON response into a ParsedResume model
"""

import json
import logging
import re
import tempfile
from pathlib import Path

import fitz  # PyMuPDF
from openai import OpenAI
from docx import Document

from app.config import get_settings
from app.models import ParsedResume

logger = logging.getLogger(__name__)

EXTRACTION_PROMPT = """
You are an expert resume parser. Given the raw text of a resume, extract all information and return it as a JSON object matching this exact schema:

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
      "responsibilities": ["string"]
    }}
  ],
  "projects": [
    {{
      "name": "string",
      "description": "string or null",
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
  "languages": ["string"]
}}

Rules:
- Return ONLY valid JSON. No markdown, no code fences, no explanatory text.
- Preserve original dates exactly as written in the resume.
- Group skills by logical categories (e.g. "Programming Languages", "Frameworks", "Tools", "Databases").
- If a field is missing, use null for scalars or [] for arrays.
- For experience, split bullet points into separate strings in the responsibilities array.
- Do not invent or infer data that is not present in the resume.

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
    # Remove ```json ... ``` or ``` ... ``` wrappers
    cleaned = re.sub(r"^```(?:json)?\s*", "", response_text.strip(), flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned.strip())
    return cleaned.strip()


def parse_resume(file_bytes: bytes, content_type: str) -> ParsedResume:
    """
    Main entry point: given raw file bytes and MIME type,
    returns a structured ParsedResume.
    """
    settings = get_settings()

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

    # 2. Call NVIDIA NIM (OpenAI-compatible API)
    client = OpenAI(
        base_url="https://integrate.api.nvidia.com/v1",
        api_key=settings.nvidia_api_key,
        timeout=60.0,
    )

    prompt = EXTRACTION_PROMPT.format(resume_text=raw_text[:12000])  # token safety limit

    completion = client.chat.completions.create(
        model="meta/llama-3.1-70b-instruct",
        messages=[
            {
                "role": "system",
                "content": "You are an expert resume parser. Always respond with valid JSON only, no markdown or explanatory text.",
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.1,
        max_tokens=4096,
    )

    response_text = completion.choices[0].message.content or ""

    # 3. Parse JSON
    cleaned = _clean_json_response(response_text)
    data = json.loads(cleaned)
    parsed = ParsedResume(**data, raw_text=raw_text)

    return parsed
