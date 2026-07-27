import fitz
import re
from typing import Dict
import tempfile
from pathlib import Path
from docx import Document

# Known section headers
SECTION_KEYWORDS = {
    "experience": ["experience", "employment", "work history"],
    "projects": ["projects", "portfolio"],
    "education": ["education", "qualifications", "academics", "schooling"],
    "skills": ["skills", "competencies", "expertise", "proficiencies"],
    "other": ["certifications", "awards", "languages", "publications", "extracurricular", "volunteer", "activities", "achievements", "honors", "interests", "leadership", "involvement"]
}

def _detect_section_header(text: str) -> str | None:
    text_clean = text.strip().lower()
    # Remove non-alphabet characters for exact matching
    text_normalized = re.sub(r'[^a-z\s]', '', text_clean).strip()
    
    if len(text_normalized) > 40 or not text_normalized:
        return None
        
    words = text_normalized.split()
    if len(words) > 4:
        return None
        
    for section, keywords in SECTION_KEYWORDS.items():
        for kw in keywords:
            # Exact match is always safe
            if text_normalized == kw:
                return section
            # If the keyword is the last word (e.g. "work experience", "technical skills")
            if len(words) > 1 and words[-1] == kw:
                return section
            # If the keyword is the first word (e.g. "skills & expertise")
            if len(words) > 1 and words[0] == kw:
                return section
                
    return None

def segment_resume_pdf(file_bytes: bytes) -> Dict[str, str]:
    sections = {
        "personal": [],
        "experience": [],
        "projects": [],
        "education": [],
        "skills": [],
        "other": []
    }
    
    current_section = "personal"
    
    with fitz.open(stream=file_bytes, filetype="pdf") as doc:
        for page in doc:
            page_dict = page.get_text("dict")
            blocks = page_dict.get("blocks", [])
            
            for block in blocks:
                if block.get("type") != 0:  # Not text
                    continue
                
                for line in block.get("lines", []):
                    line_text_parts = []
                    is_header_candidate = False
                    
                    for span in line.get("spans", []):
                        text = span.get("text", "").strip()
                        if not text:
                            continue
                        
                        line_text_parts.append(text)
                        
                        is_bold = (span.get("flags", 0) & 16) != 0
                        is_upper = text.isupper()
                        size = span.get("size", 10)
                        
                        if is_bold or is_upper or size > 11:
                            is_header_candidate = True
                            
                    full_line_text = " ".join(line_text_parts).strip()
                    if not full_line_text:
                        continue
                        
                    if is_header_candidate and len(full_line_text) < 40:
                        detected = _detect_section_header(full_line_text)
                        if detected:
                            current_section = detected
                            
                    sections[current_section].append(full_line_text)
            
            # Extract invisible hyperlinks from the page
            for link in page.get_links():
                if link.get("uri"):
                    sections[current_section].append(f"[Hyperlink found on page]: {link['uri']}")
                        
    return {k: "\n".join(v) for k, v in sections.items()}

def segment_resume_docx(file_bytes: bytes) -> Dict[str, str]:
    sections = {
        "personal": [],
        "experience": [],
        "projects": [],
        "education": [],
        "skills": [],
        "other": []
    }
    
    current_section = "personal"
    
    with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp:
        tmp.write(file_bytes)
        tmp_path = Path(tmp.name)

    try:
        doc = Document(str(tmp_path))
        for para in doc.paragraphs:
            text = para.text.strip()
            if not text:
                continue
                
            if len(text) < 40:
                detected = _detect_section_header(text)
                if detected:
                    current_section = detected
                    
            sections[current_section].append(text)
            
        return {k: "\n".join(v) for k, v in sections.items()}
    finally:
        tmp_path.unlink(missing_ok=True)

def segment_resume(file_bytes: bytes, content_type: str) -> Dict[str, str]:
    if content_type == "application/pdf":
        return segment_resume_pdf(file_bytes)
    elif content_type in (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/msword",
    ):
        return segment_resume_docx(file_bytes)
    else:
        raise ValueError(f"Unsupported file type: {content_type}")
