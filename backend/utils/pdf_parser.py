"""
PDF parser for JD and Resume documents.

Uses PyMuPDF to extract raw text, then an LLM to parse
structured data. Falls back to regex extraction if the LLM fails.
"""

import re
import logging
from pathlib import Path
from typing import Any

import fitz  # PyMuPDF

from backend.llm.provider import llm_invoke_json, LLMProviderError

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Raw text extraction
# ---------------------------------------------------------------------------

def extract_text_from_pdf(path: str | Path) -> str:
    """Extract all text from a PDF file using PyMuPDF.

    Args:
        path: Absolute path to the PDF file.

    Returns:
        Concatenated plain text from all pages.

    Raises:
        FileNotFoundError: If the PDF does not exist.
        fitz.FileDataError: If the file is not a valid PDF.
    """
    doc = fitz.open(str(path))
    pages: list[str] = []
    for page in doc:
        pages.append(page.get_text())
    doc.close()
    return "\n".join(pages).strip()


# ---------------------------------------------------------------------------
# JD Parser
# ---------------------------------------------------------------------------

_JD_PROMPT = """\
You are an expert HR data extractor.
Extract structured information from the job description text below.

Return ONLY a JSON object with these exact keys:
{{
  "job_title": "string",
  "company": "string or empty string",
  "location": "string",
  "employment_type": "string",
  "experience_required": "string",
  "salary_range": "string or empty string",
  "required_skills": ["list", "of", "strings"],
  "nice_to_have_skills": ["list", "of", "strings"],
  "responsibilities": ["list", "of", "strings"],
  "qualifications": ["list", "of", "strings"]
}}

Job Description Text:
---
{text}
---
"""

_RESUME_PROMPT = """\
You are an expert HR data extractor.
Extract structured information from the resume text below.

Return ONLY a JSON object with these exact keys:
{{
  "candidate_name": "string",
  "email": "string or empty string",
  "phone": "string or empty string",
  "current_role": "string",
  "total_experience_years": 0,
  "skills": ["list", "of", "strings"],
  "experience": [
    {{
      "company": "string",
      "role": "string",
      "duration": "string",
      "highlights": ["list", "of", "strings"]
    }}
  ],
  "education": [
    {{
      "institution": "string",
      "degree": "string",
      "year": "string"
    }}
  ]
}}

Resume Text:
---
{text}
---
"""


def _regex_extract_skills(text: str) -> list[str]:
    """Attempt to extract skills from text using common patterns.

    Args:
        text: Raw text to search.

    Returns:
        List of skill strings found, may be empty.
    """
    common_skills = [
        "Python", "JavaScript", "TypeScript", "PHP", "Laravel", "React",
        "Vue", "Angular", "Node.js", "FastAPI", "Django", "Flask",
        "MySQL", "PostgreSQL", "MongoDB", "Redis", "Docker", "Kubernetes",
        "AWS", "GCP", "Azure", "Git", "REST", "GraphQL", "HTML", "CSS",
        "Java", "C#", "C++", "Go", "Rust", "Swift", "Kotlin",
    ]
    found = [s for s in common_skills if re.search(r"\b" + re.escape(s) + r"\b", text, re.IGNORECASE)]
    return found


def _regex_jd_fallback(text: str) -> dict[str, Any]:
    """Regex-based fallback parser for job descriptions.

    Args:
        text: Raw JD text.

    Returns:
        Partially filled JD dict with whatever could be extracted.
    """
    logger.warning("Using regex fallback for JD parsing")
    skills = _regex_extract_skills(text)
    # Try to find job title on the first non-empty line
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    job_title = lines[0] if lines else ""
    return {
        "job_title": job_title,
        "company": "",
        "location": "",
        "employment_type": "",
        "experience_required": "",
        "salary_range": "",
        "required_skills": skills,
        "nice_to_have_skills": [],
        "responsibilities": [],
        "qualifications": [],
    }


def _regex_resume_fallback(text: str) -> dict[str, Any]:
    """Regex-based fallback parser for resumes.

    Args:
        text: Raw resume text.

    Returns:
        Partially filled resume dict with whatever could be extracted.
    """
    logger.warning("Using regex fallback for resume parsing")
    skills = _regex_extract_skills(text)

    # Try to find email
    email_match = re.search(r"[\w.+-]+@[\w-]+\.[a-zA-Z]{2,}", text)
    email = email_match.group(0) if email_match else ""

    # Try to find phone
    phone_match = re.search(r"[\+\d][\d\s\-().]{7,15}\d", text)
    phone = phone_match.group(0).strip() if phone_match else ""

    # First non-empty line as name guess
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    candidate_name = lines[0] if lines else ""

    return {
        "candidate_name": candidate_name,
        "email": email,
        "phone": phone,
        "current_role": "",
        "total_experience_years": 0,
        "skills": skills,
        "experience": [],
        "education": [],
    }


async def parse_jd(path: str | Path) -> dict[str, Any]:
    """Parse a Job Description PDF into structured data.

    Extracts raw text via PyMuPDF, then uses the LLM to produce
    a structured dict. Falls back to regex if the LLM fails.

    Args:
        path: Path to the JD PDF file.

    Returns:
        Dict with keys: job_title, company, location, employment_type,
        experience_required, salary_range, required_skills,
        nice_to_have_skills, responsibilities, qualifications, raw_text.
    """
    raw_text = extract_text_from_pdf(path)
    prompt = _JD_PROMPT.format(text=raw_text[:8000])  # cap to avoid token limits

    try:
        result = await llm_invoke_json([
            {"role": "user", "content": prompt}
        ])
        result["raw_text"] = raw_text
        return result
    except (LLMProviderError, Exception) as e:
        logger.error("LLM JD parsing failed: %s", e)
        fallback = _regex_jd_fallback(raw_text)
        fallback["raw_text"] = raw_text
        return fallback


async def parse_resume(
    path: str | Path,
    jd_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Parse a Resume PDF into structured data, with optional JD match scoring.

    Extracts raw text via PyMuPDF, then uses the LLM to produce
    a structured dict. If jd_data is provided, computes a match score
    against required skills. Falls back to regex if the LLM fails.

    Args:
        path: Path to the resume PDF file.
        jd_data: Optional parsed JD dict to compute skill match score.

    Returns:
        Dict with keys: candidate_name, email, phone, current_role,
        total_experience_years, skills, experience, education,
        match_score, matched_skills, missing_skills, raw_text.
    """
    raw_text = extract_text_from_pdf(path)
    prompt = _RESUME_PROMPT.format(text=raw_text[:8000])

    try:
        result = await llm_invoke_json([
            {"role": "user", "content": prompt}
        ])
    except (LLMProviderError, Exception) as e:
        logger.error("LLM resume parsing failed: %s", e)
        result = _regex_resume_fallback(raw_text)

    result["raw_text"] = raw_text

    # Compute match score against JD if provided
    if jd_data:
        required: list[str] = jd_data.get("required_skills", [])
        nice: list[str] = jd_data.get("nice_to_have_skills", [])
        all_jd_skills = required + nice
        candidate_skills_lower = {s.lower() for s in result.get("skills", [])}

        matched = [s for s in all_jd_skills if s.lower() in candidate_skills_lower]
        missing = [s for s in required if s.lower() not in candidate_skills_lower]

        match_score = (
            round(len(matched) / len(all_jd_skills) * 100)
            if all_jd_skills else 0
        )

        result["match_score"] = match_score
        result["matched_skills"] = matched
        result["missing_skills"] = missing
    else:
        result.setdefault("match_score", 0)
        result.setdefault("matched_skills", [])
        result.setdefault("missing_skills", [])

    return result
