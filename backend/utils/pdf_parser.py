"""
PDF parser for JD and Resume documents.

Uses PyMuPDF to extract raw text, then an LLM to parse
structured data. Falls back to regex extraction if the LLM fails.

Also includes skill_rules generator which creates per-skill interview
strategies based on JD requirements + candidate resume evidence.
"""

import re
import logging
from pathlib import Path
from typing import Any

import fitz  # PyMuPDF

from backend.llm.provider import llm_invoke_json, llm_invoke, LLMProviderError, last_provider_used
import backend.llm.provider as llm_provider

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Raw text extraction
# ---------------------------------------------------------------------------

def extract_text_from_pdf(source: str | Path | bytes) -> str:
    """Extract all text from a PDF using PyMuPDF with improved extraction.

    Uses multiple extraction strategies to handle different PDF layouts:
    1. Standard text extraction per page
    2. Falls back to block-level extraction for better column handling

    Args:
        source: File path or raw PDF bytes for in-memory processing.

    Returns:
        Concatenated plain text from all pages, cleaned up.
    """
    if isinstance(source, bytes):
        doc = fitz.open(stream=source, filetype="pdf")
    else:
        doc = fitz.open(str(source))

    pages: list[str] = []
    for page in doc:
        # Try standard extraction first
        text = page.get_text("text")

        # If text is suspiciously short, try block-level extraction
        # which handles multi-column layouts better
        if len(text.strip()) < 50:
            blocks = page.get_text("blocks")
            block_texts = []
            for block in sorted(blocks, key=lambda b: (b[1], b[0])):
                if block[6] == 0:  # text block (not image)
                    block_texts.append(block[4].strip())
            alt_text = "\n".join(block_texts)
            if len(alt_text) > len(text):
                text = alt_text

        pages.append(text)

    doc.close()

    # Clean up extracted text
    raw = "\n".join(pages).strip()
    # Collapse excessive blank lines
    raw = re.sub(r"\n{3,}", "\n\n", raw)
    # Fix common PDF extraction artifacts
    raw = re.sub(r"(\w)-\n(\w)", r"\1\2", raw)  # rejoin hyphenated words
    return raw


# ---------------------------------------------------------------------------
# JD Parser
# ---------------------------------------------------------------------------

_JD_PROMPT = """\
You are an expert HR recruiter and data extraction specialist. Your task is to
thoroughly analyze the job description text below and extract ALL relevant
information with high accuracy.

EXTRACTION RULES:
1. Read the ENTIRE text carefully before extracting. Do not skip sections.
2. For job_title: Extract the EXACT title as written (e.g. "Senior Full-Stack Developer", not just "Developer").
3. For company: Look for the company/organization name in headers, footers, "About Us", or "Company:" fields.
4. For location: Include city, state/province, and country if available. Note if remote/hybrid is mentioned.
5. For employment_type: Full-time, Part-time, Contract, Freelance, Internship — extract exactly as stated.
6. For experience_required: Extract the specific years/level (e.g. "3-5 years", "Senior level", "Entry level").
7. For salary_range: Extract exact figures if mentioned (e.g. "PHP 30,000-50,000/month", "$80K-$120K/year").
8. For required_skills: List EVERY specific technology, tool, framework, language, and methodology mentioned
   as required. Be granular — "Laravel" and "PHP" are separate skills. Include version numbers if specified.
   Also include soft skills if explicitly required (e.g. "strong communication", "teamwork").
9. For nice_to_have_skills: Technologies and skills listed as "preferred", "bonus", "nice to have", "a plus".
10. For responsibilities: List ALL job duties and responsibilities mentioned. Be specific and complete.
11. For qualifications: List ALL educational requirements, certifications, and other qualifications.

Return ONLY a JSON object with these exact keys:
{{
  "job_title": "exact job title string",
  "company": "company name or empty string if not found",
  "location": "full location string or empty string",
  "employment_type": "employment type or empty string",
  "experience_required": "experience requirement string or empty string",
  "salary_range": "salary range string or empty string",
  "required_skills": ["every", "single", "required", "skill", "technology", "tool"],
  "nice_to_have_skills": ["preferred", "bonus", "skills"],
  "responsibilities": ["detailed", "list", "of", "all", "responsibilities"],
  "qualifications": ["all", "educational", "and", "certification", "requirements"]
}}

IMPORTANT:
- Extract skills from ALL sections — requirements, responsibilities, qualifications, description.
- If a skill appears in responsibilities ("Build REST APIs using Node.js"), extract both "REST APIs" and "Node.js".
- Do NOT merge similar skills — "React" and "React Native" are separate entries.
- Do NOT invent or assume skills not mentioned in the text.
- If a section is empty or not found, use an empty string or empty array.

Job Description Text:
---
{text}
---
"""

_RESUME_PROMPT = """\
You are an expert HR recruiter and resume parser. Your task is to thoroughly
analyze the resume text below and extract ALL relevant information with high
accuracy and completeness.

EXTRACTION RULES:
1. Read the ENTIRE resume text carefully. PDFs may have jumbled ordering — reconstruct logically.
2. For candidate_name: Extract the full name (usually at the top or in a header).
3. For email: Find ANY email address in the document.
4. For phone: Find ANY phone number (may include country code like +63).
5. For current_role: The most recent job title, or "Student" / "Fresh Graduate" if no work experience.
6. For total_experience_years: Calculate from work history. If fresh graduate, use 0.
   Count from earliest start date to latest end date (or present).
7. For skills: Extract EVERY technology, tool, framework, programming language, database,
   methodology, platform, and relevant soft skill mentioned ANYWHERE in the resume.
   Be thorough — check the skills section, project descriptions, work experience bullet points,
   certifications, and education. Include:
   - Programming languages (Python, PHP, JavaScript, Java, C#, etc.)
   - Frameworks/Libraries (Laravel, React, Vue.js, Django, Spring Boot, etc.)
   - Databases (MySQL, PostgreSQL, MongoDB, Redis, etc.)
   - Tools/Platforms (Docker, Git, AWS, Azure, Figma, Jira, etc.)
   - Methodologies (Agile, Scrum, REST API, CI/CD, TDD, etc.)
   - Soft skills if notable (Leadership, Project Management, etc.)
8. For experience: Extract ALL work entries with company, exact role title, duration
   (e.g. "Jan 2022 - Present"), and specific accomplishments/highlights.
   For highlights, be detailed — include metrics, technologies used, and outcomes.
9. For education: Extract ALL educational entries with institution, degree/course, and year.
   Include certifications, bootcamps, and relevant training programs.

Return ONLY a JSON object with these exact keys:
{{
  "candidate_name": "Full Name",
  "email": "email@example.com or empty string",
  "phone": "phone number or empty string",
  "current_role": "most recent job title",
  "total_experience_years": 0,
  "skills": ["comprehensive", "list", "of", "every", "skill", "mentioned"],
  "experience": [
    {{
      "company": "Company Name",
      "role": "Exact Job Title",
      "duration": "Start Date - End Date",
      "highlights": [
        "Specific accomplishment with technologies and metrics if available",
        "Another detailed achievement"
      ]
    }}
  ],
  "education": [
    {{
      "institution": "School/University Name",
      "degree": "Degree/Course/Certification",
      "year": "Year or date range"
    }}
  ]
}}

IMPORTANT:
- Extract skills from ALL sections, not just a "Skills" section.
- If experience mentions "Built a REST API using Laravel and MySQL", extract: Laravel, MySQL, REST API, PHP.
- Project sections count as experience — include personal/academic projects under experience.
- Do NOT invent information not present in the text.
- If ANY field cannot be found, use empty string or empty array.
- For total_experience_years, round to the nearest integer.

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


async def parse_jd(source: str | Path | bytes) -> dict[str, Any]:
    """Parse a Job Description PDF into structured data.

    Extracts raw text via PyMuPDF, then uses the LLM to produce
    a structured dict. Falls back to regex if the LLM fails.

    Args:
        source: Path to the JD PDF file, or raw PDF bytes.

    Returns:
        Dict with keys: job_title, company, location, employment_type,
        experience_required, salary_range, required_skills,
        nice_to_have_skills, responsibilities, qualifications, raw_text.
    """
    raw_text = extract_text_from_pdf(source)

    if not raw_text.strip():
        logger.error("parse_jd: PDF text extraction returned empty text")
        fallback = _regex_jd_fallback("")
        fallback["raw_text"] = ""
        return fallback

    logger.info("parse_jd: Extracted %d chars from PDF", len(raw_text))

    # Send more text to the LLM for thorough analysis (up to 15k chars)
    prompt = _JD_PROMPT.format(text=raw_text[:15000])

    try:
        result = await llm_invoke_json([
            {"role": "system", "content": "You are an expert HR data extraction specialist. Extract information accurately and completely. Respond with valid JSON only."},
            {"role": "user", "content": prompt},
        ])
        # Validate required fields are present and non-empty
        if not result.get("required_skills"):
            logger.warning("parse_jd: LLM returned no required_skills, enriching with regex")
            regex_skills = _regex_extract_skills(raw_text)
            if regex_skills:
                result["required_skills"] = regex_skills

        result["raw_text"] = raw_text
        logger.info(
            "\n" + "*" * 60 + "\n"
            "  JD ANALYSIS COMPLETE\n"
            "  Model used: %s\n"
            "  Job title: %s\n"
            "  Company: %s\n"
            "  Required skills (%d): %s\n"
            "  Nice-to-have (%d): %s\n"
            "  Responsibilities: %d\n"
            "  Qualifications: %d\n"
            + "*" * 60,
            llm_provider.last_provider_used,
            result.get("job_title", "(not found)"),
            result.get("company", "(not found)"),
            len(result.get("required_skills", [])),
            ", ".join(result.get("required_skills", [])[:10]),
            len(result.get("nice_to_have_skills", [])),
            ", ".join(result.get("nice_to_have_skills", [])[:10]),
            len(result.get("responsibilities", [])),
            len(result.get("qualifications", [])),
        )
        return result
    except (LLMProviderError, Exception) as e:
        logger.error("LLM JD parsing failed: %s", e)
        fallback = _regex_jd_fallback(raw_text)
        fallback["raw_text"] = raw_text
        return fallback


async def parse_resume(
    source: str | Path | bytes,
    jd_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Parse a Resume PDF into structured data, with optional JD match scoring.

    Extracts raw text via PyMuPDF, then uses the LLM to produce
    a structured dict. If jd_data is provided, computes a match score
    against required skills using fuzzy matching. Falls back to regex
    if the LLM fails.

    Args:
        source: Path to the resume PDF file, or raw PDF bytes.
        jd_data: Optional parsed JD dict to compute skill match score.

    Returns:
        Dict with keys: candidate_name, email, phone, current_role,
        total_experience_years, skills, experience, education,
        match_score, matched_skills, missing_skills, raw_text.
    """
    raw_text = extract_text_from_pdf(source)

    if not raw_text.strip():
        logger.error("parse_resume: PDF text extraction returned empty text")
        fallback = _regex_resume_fallback("")
        fallback["raw_text"] = ""
        fallback.setdefault("match_score", 0)
        fallback.setdefault("matched_skills", [])
        fallback.setdefault("missing_skills", [])
        return fallback

    logger.info("parse_resume: Extracted %d chars from PDF", len(raw_text))

    # Send more text to the LLM (up to 15k chars)
    prompt = _RESUME_PROMPT.format(text=raw_text[:15000])

    try:
        result = await llm_invoke_json([
            {"role": "system", "content": "You are an expert HR resume parser. Extract information accurately and completely. Respond with valid JSON only."},
            {"role": "user", "content": prompt},
        ])
        # Validate and enrich skills if LLM missed some
        llm_skills = result.get("skills", [])
        regex_skills = _regex_extract_skills(raw_text)
        # Merge regex-found skills that LLM missed
        llm_skills_lower = {s.lower() for s in llm_skills}
        for rs in regex_skills:
            if rs.lower() not in llm_skills_lower:
                llm_skills.append(rs)
        result["skills"] = llm_skills

        logger.info(
            "\n" + "*" * 60 + "\n"
            "  RESUME ANALYSIS COMPLETE\n"
            "  Model used: %s\n"
            "  Candidate: %s\n"
            "  Email: %s\n"
            "  Current role: %s\n"
            "  Experience: %d years\n"
            "  Skills (%d): %s\n"
            "  Work entries: %d\n"
            "  Education entries: %d\n"
            + "*" * 60,
            llm_provider.last_provider_used,
            result.get("candidate_name", "(not found)"),
            result.get("email", "(not found)"),
            result.get("current_role", "(not found)"),
            result.get("total_experience_years", 0),
            len(result.get("skills", [])),
            ", ".join(result.get("skills", [])[:15]),
            len(result.get("experience", [])),
            len(result.get("education", [])),
        )
    except (LLMProviderError, Exception) as e:
        logger.error("LLM resume parsing failed: %s", e)
        result = _regex_resume_fallback(raw_text)

    result["raw_text"] = raw_text

    # Compute match score against JD if provided — using fuzzy matching
    if jd_data:
        required: list[str] = jd_data.get("required_skills", [])
        nice: list[str] = jd_data.get("nice_to_have_skills", [])
        candidate_skills = result.get("skills", [])
        candidate_text_lower = raw_text.lower()

        matched = []
        missing = []

        # Build normalized candidate skill set for matching
        candidate_skills_lower = {s.lower().strip() for s in candidate_skills}

        for jd_skill in required + nice:
            skill_lower = jd_skill.lower().strip()
            is_matched = False

            # 1. Exact match in extracted skills
            if skill_lower in candidate_skills_lower:
                is_matched = True
            else:
                # 2. Partial / fuzzy match: check if skill words appear in candidate skills
                skill_words = skill_lower.split()
                for cs in candidate_skills_lower:
                    # Check if the JD skill is a substring of a candidate skill or vice versa
                    if skill_lower in cs or cs in skill_lower:
                        is_matched = True
                        break
                    # Check word-level overlap (e.g. "REST API" matches "RESTful APIs")
                    cs_words = cs.split()
                    overlap = sum(1 for w in skill_words if any(w in cw or cw in w for cw in cs_words))
                    if overlap >= len(skill_words) * 0.6:
                        is_matched = True
                        break

                # 3. Check raw resume text as last resort (skill mentioned but not extracted)
                if not is_matched:
                    # For multi-word skills, check if most words appear near each other
                    if len(skill_words) == 1:
                        # Use word boundary for single-word skills to avoid false positives
                        pattern = r"\b" + re.escape(skill_lower) + r"\b"
                        if re.search(pattern, candidate_text_lower):
                            is_matched = True
                    else:
                        # For multi-word, check if words appear in the text
                        words_found = sum(1 for w in skill_words if w in candidate_text_lower)
                        if words_found >= len(skill_words) * 0.7:
                            is_matched = True

            if is_matched:
                matched.append(jd_skill)
            elif jd_skill in required:
                missing.append(jd_skill)

        # Weighted scoring: required skills worth 2x, nice-to-have worth 1x
        required_matched = len([s for s in matched if s in required])
        nice_matched = len([s for s in matched if s in nice])
        total_weight = len(required) * 2 + len(nice) * 1
        matched_weight = required_matched * 2 + nice_matched * 1

        match_score = round(matched_weight / total_weight * 100) if total_weight > 0 else 0

        result["match_score"] = match_score
        result["matched_skills"] = matched
        result["missing_skills"] = missing

        logger.info(
            "\n" + "#" * 60 + "\n"
            "  SKILL MATCH SCORING\n"
            "  JD required skills (%d): %s\n"
            "  JD nice-to-have (%d): %s\n"
            "  Candidate skills (%d): %s\n"
            "  Matched (%d): %s\n"
            "  Missing (%d): %s\n"
            "  MATCH SCORE: %d%%\n"
            + "#" * 60,
            len(required), ", ".join(required[:10]),
            len(nice), ", ".join(nice[:10]),
            len(candidate_skills), ", ".join(candidate_skills[:15]),
            len(matched), ", ".join(matched[:10]),
            len(missing), ", ".join(missing[:10]),
            match_score,
        )
    else:
        result.setdefault("match_score", 0)
        result.setdefault("matched_skills", [])
        result.setdefault("missing_skills", [])

    return result


# ---------------------------------------------------------------------------
# Skill Rules Generator — per-skill interview strategies
# ---------------------------------------------------------------------------

_SKILL_RULES_PROMPT = """\
You are an expert technical interviewer. Given the JD skills and candidate resume below,
generate a UNIQUE interview angle for each skill so ARIA asks DISTINCT questions.

CRITICAL:
- Each skill MUST have a DIFFERENT angle/focus — NO TWO SKILLS should lead to the same question type.
- For programming languages (PHP, Python, etc): Ask about language-specific features, not general coding.
- For frameworks (Laravel, React, etc): Ask about framework patterns, NOT the underlying language.
- For databases (MySQL, PostgreSQL): Ask about schema design, queries, NOT just "how do you use it".
- For infrastructure (AWS, Docker): Ask about architecture decisions, deployment, scaling.
- If resume shows evidence of using the skill, reference it specifically in the sample question.
- If resume lacks evidence, the sample question should probe if they actually have the skill.

JOB TITLE: {job_title}

REQUIRED SKILLS:
{required_skills}

CANDIDATE RESUME SUMMARY:
- Name: {candidate_name}
- Current role: {current_role}
- Experience: {experience_years} years
- Skills listed: {candidate_skills}
- Recent work:
{experience_summary}

Reply with a JSON array. Each entry:
{{
  "skill": "exact skill name from JD",
  "angle": "specific focus area (e.g. 'ORM patterns' not just 'Laravel')",
  "resume_evidence": "what the resume shows about this skill, or 'No evidence found'",
  "sample_question": "a SPECIFIC question targeting this angle"
}}

IMPORTANT:
- Output {num_skills} entries, one per skill.
- Make sample_question specific — "Tell me about your experience with X" is too generic.
- Good: "In your payroll system, how did you handle N+1 queries in Laravel's Eloquent?"
- Bad: "Tell me about your Laravel experience."
"""


async def generate_skill_rules(
    jd_data: dict[str, Any],
    resume_data: dict[str, Any],
) -> list[dict[str, str]]:
    """Generate per-skill interview rules from JD + resume analysis.

    Creates a unique interview angle for each required skill based on
    the candidate's resume evidence, preventing repetitive questions.

    Args:
        jd_data: Parsed JD dict with required_skills, job_title, etc.
        resume_data: Parsed resume dict with skills, experience, etc.

    Returns:
        List of skill rule dicts, each with: skill, angle, resume_evidence, sample_question.
    """
    required_skills = jd_data.get("required_skills", [])
    nice_to_have = jd_data.get("nice_to_have_skills", [])
    all_skills = required_skills + [s for s in nice_to_have if s not in required_skills]

    if not all_skills:
        logger.warning("generate_skill_rules: No skills to generate rules for")
        return []

    # Build experience summary from resume
    experience_entries = resume_data.get("experience", [])
    exp_lines = []
    for exp in experience_entries[:3]:  # Last 3 jobs
        company = exp.get("company", "")
        role = exp.get("role", "")
        highlights = exp.get("highlights", [])
        if company and role:
            exp_lines.append(f"  - {role} at {company}")
            for h in highlights[:2]:
                exp_lines.append(f"    • {h}")
    experience_summary = "\n".join(exp_lines) if exp_lines else "  No work experience listed."

    prompt = _SKILL_RULES_PROMPT.format(
        job_title=jd_data.get("job_title", "Software Developer"),
        required_skills="\n".join(f"  - {s}" for s in all_skills[:12]),
        candidate_name=resume_data.get("candidate_name", "Candidate"),
        current_role=resume_data.get("current_role", "Unknown"),
        experience_years=resume_data.get("total_experience_years", 0),
        candidate_skills=", ".join(resume_data.get("skills", [])[:20]),
        experience_summary=experience_summary,
        num_skills=len(all_skills[:12]),
    )

    try:
        result = await llm_invoke_json([
            {"role": "system", "content": "You are an expert technical interviewer. Generate unique interview angles for each skill. Reply with valid JSON array only."},
            {"role": "user", "content": prompt},
        ])

        rules = []
        if isinstance(result, list):
            rules = result
        elif isinstance(result, dict) and "skills" in result:
            rules = result["skills"]
        elif isinstance(result, dict):
            # Try to extract array from dict
            for key in result:
                if isinstance(result[key], list):
                    rules = result[key]
                    break

        # Validate and clean
        valid_rules = []
        for r in rules:
            if isinstance(r, dict) and r.get("skill") and r.get("angle"):
                valid_rules.append({
                    "skill": str(r.get("skill", "")),
                    "angle": str(r.get("angle", "")),
                    "resume_evidence": str(r.get("resume_evidence", "No evidence found")),
                    "sample_question": str(r.get("sample_question", "")),
                })

        logger.info(
            "\n" + "=" * 60 + "\n"
            "  SKILL RULES GENERATED\n"
            "  Skills covered: %d\n"
            "  Rules:\n%s\n"
            + "=" * 60,
            len(valid_rules),
            "\n".join(f"    {r['skill']}: {r['angle']}" for r in valid_rules[:10]),
        )
        return valid_rules

    except Exception as e:
        logger.error("generate_skill_rules failed: %s", e)
        # Fallback: basic rules without LLM
        return [
            {
                "skill": skill,
                "angle": "general proficiency",
                "resume_evidence": "Check resume",
                "sample_question": f"Tell me about your experience with {skill}.",
            }
            for skill in all_skills[:10]
        ]

