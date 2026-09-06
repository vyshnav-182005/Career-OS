"""
Resume Parser — Core extraction and profile intelligence logic.

Pipeline:
  1. Extract raw text from PDF/DOCX using a block-aware Layout Segmenter
  2. Map text into logical sections (Experience, Projects, Education, etc.)
  3. Single LLM Call (Extract JSON from already-separated sections)
  4. Pydantic validation via ParsedResume.
"""

import json
import logging
import re
from typing import Tuple, Any, Dict
from fastapi import UploadFile, BackgroundTasks

from backend.config import settings
from backend.services.llm_client import NO_THINKING, build_client
from backend.models.resume import ParsedResume
from backend.db.supabase_client import upsert_parsed_resume
from backend.services.workflow_orchestrator import trigger_profile_intelligence_workflow
from backend.services.document_segmenter import segment_resume

logger = logging.getLogger(__name__)

PARSE_RESUME_PROMPT = """
You are an expert resume parser. I have pre-segmented the resume into XML-like tags to prevent context bleeding. 
Your task is to extract all structured data into a JSON object matching this EXACT schema:

{
  "personal_info": {
    "name": "string or null",
    "email": "string or null",
    "phone": "string or null",
    "location": "string or null",
    "linkedin": "string or null",
    "github": "string or null",
    "website": "string or null",
    "summary": "string or null"
  },
  "education": [
    {
      "institution": "string",
      "degree": "string or null",
      "field_of_study": "string or null",
      "start_date": "string or null",
      "end_date": "string or null",
      "gpa": "string or null",
      "description": "string or null"
    }
  ],
  "experience": [
    {
      "company": "string",
      "title": "string",
      "location": "string or null",
      "start_date": "string or null",
      "end_date": "string or null",
      "is_current": false,
      "responsibilities": ["string (split bullet points exactly as they appear)"]
    }
  ],
  "projects": [
    {
      "name": "string",
      "description": ["string (split bullet points exactly as they appear)"],
      "technologies": ["string"],
      "url": "string or null",
      "start_date": "string or null",
      "end_date": "string or null"
    }
  ],
  "certifications": [
    {
      "name": "string",
      "issuer": "string or null",
      "date": "string or null",
      "expiry": "string or null",
      "credential_id": "string or null"
    }
  ],
  "skills": [
    {
      "category": "string",
      "skills": ["string"]
    }
  ],
  "languages": ["string"],
  "publications": [
    {
      "title": "string",
      "publisher": "string or null",
      "date": "string or null",
      "url": "string or null",
      "description": "string or null"
    }
  ],
  "custom_sections": [
    {
      "section_title": "string (e.g., 'Awards', 'Volunteer Work')",
      "items": [
        {
          "title": "string or null",
          "subtitle": "string or null",
          "date": "string or null",
          "description": "string or null"
        }
      ]
    }
  ]
}

CRITICAL RULES:
1. Return ONLY valid JSON matching the schema above.
2. Experience vs Projects: You MUST NOT place any projects (from <Projects> tag) into the `experience` array. The `experience` array MUST ONLY come from the <Experience> tag. If the <Experience> tag is empty or does not contain real employment, return an empty array [] for experience.
3. Link Extraction: Place LinkedIn links ONLY in `linkedin` and GitHub links ONLY in `github`. DO NOT extract literal words like 'GitHub' if there is no actual URL or username provided.
4. Skills Extraction (CRITICAL): You MUST extract EVERY SINGLE skill mentioned in the <Skills> tag exactly as written. Do not summarize, truncate, or omit any information. If the text groups skills into distinct categories, you MUST preserve those exact groupings by creating a separate object in the `skills` array for each category. Do not lump everything under a generic category.
5. Comma-Separated Skills: If skills are provided as a comma-separated list, split them into individual strings in the array (e.g., ["Python", "Java"] NOT ["Python, Java"]).

Segmented Resume Text:
---
<Personal>
{personal}
</Personal>
<Education>
{education}
</Education>
<Experience>
{experience}
</Experience>
<Projects>
{projects}
</Projects>
<Skills>
{skills}
</Skills>
<Other>
{other}
</Other>
---
"""

def _clean_json_response(response_text: str) -> str:
    cleaned = re.sub(r"^```(?:json)?\s*", "", response_text.strip(), flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned.strip())
    return cleaned.strip()

def parse_resume(file_bytes: bytes, content_type: str) -> ParsedResume:
    # 1. Layout-Aware Segmentation
    sections = segment_resume(file_bytes, content_type)
    
    # Concatenate raw text for the final object and embedding
    raw_text = "\n\n".join(sections.values()).strip()
    if not raw_text:
        raise ValueError("Could not extract any text from the uploaded file.")
        
    logger.info("Extracted %d characters from resume (Segmented)", len(raw_text))

    # 2. Single LLM Extraction with explicit XML bounds
    client = build_client(timeout=120.0)
    
    prompt = PARSE_RESUME_PROMPT.replace("{personal}", sections.get("personal", ""))
    prompt = prompt.replace("{education}", sections.get("education", ""))
    prompt = prompt.replace("{experience}", sections.get("experience", ""))
    prompt = prompt.replace("{projects}", sections.get("projects", ""))
    prompt = prompt.replace("{skills}", sections.get("skills", ""))
    prompt = prompt.replace("{other}", sections.get("other", ""))
    
    completion = client.chat.completions.create(
        model=settings.model,
        messages=[
            {
                "role": "system",
                "content": "You are an expert resume parser. Always respond with valid JSON only, no markdown.",
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.1,
        max_tokens=4096,
        response_format={"type": "json_object"},
        extra_body=NO_THINKING,
    )
    
    response_text = completion.choices[0].message.content or ""
    cleaned = _clean_json_response(response_text)
    
    try:
        merged_data = json.loads(cleaned)
    except Exception as e:
        logger.error(f"Error parsing JSON: {e}")
        merged_data = {}
        
    merged_data["raw_text"] = raw_text
    
    # Cross-section Consistency & Cleanup
    if merged_data.get("experience") is None:
        merged_data["experience"] = []
        
    if merged_data.get("projects") is None:
        merged_data["projects"] = []
        
    project_names = {p.get("name", "").lower() for p in merged_data["projects"] if p.get("name")}
    cleaned_experience = []
    for exp in merged_data.get("experience", []):
        comp = exp.get("company", "").lower()
        if comp and comp in project_names:
            continue
        cleaned_experience.append(exp)
    merged_data["experience"] = cleaned_experience

    # Pydantic Validation
    parsed = ParsedResume(**merged_data)
    logger.info("Resume parsing complete (Single Call)")
    
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

    # Call the concurrent multi-stage parser
    parsed = parse_resume(file_bytes, content_type)
    
    # Upload to Supabase and update profiles table with initial data
    upsert_parsed_resume(user_id, parsed, file_bytes, content_type, filename)
    
    # Trigger GitHub enrichment and profile intelligence agent in the background
    github_url = parsed.personal_info.github if parsed.personal_info else None
    
    if github_url:
        from backend.services.github_enrichment import enrich_and_trigger_workflow
        background_tasks.add_task(enrich_and_trigger_workflow, user_id, github_url)
    else:
        background_tasks.add_task(trigger_profile_intelligence_workflow, user_id)
    
    return parsed, filename, content_type
