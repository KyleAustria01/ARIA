"""
analyze_resume_node — LangGraph node for Resume analysis.

Receives the path to an uploaded resume PDF, parses it into structured
data using pdf_parser (with JD context for match scoring), and populates
all resume fields in InterviewState.
Pure function: takes state, returns updated state dict.
"""

import logging

from backend.interview_graph.state import InterviewState
from backend.utils.gender_detector import (
    detect_gender_from_name,
    get_candidate_address,
)
from backend.utils.pdf_parser import parse_resume

logger = logging.getLogger(__name__)


def get_match_tier(score: float) -> dict:
    """Convert a numeric match score to a simplified tier label.

    Args:
        score: Numeric match percentage (0-100).

    Returns:
        Dict with tier, label, color, description, and icon.
    """
    if score >= 90:
        return {
            "tier": "Excellent Match",
            "label": "Excellent",
            "color": "green",
            "description": "Candidate meets all requirements",
            "icon": "🟢",
        }
    elif score >= 65:
        return {
            "tier": "Good Match",
            "label": "Good",
            "color": "blue",
            "description": "Candidate meets most requirements",
            "icon": "🔵",
        }
    elif score >= 30:
        return {
            "tier": "Partial Match",
            "label": "Partial",
            "color": "yellow",
            "description": "Candidate meets some requirements",
            "icon": "🟡",
        }
    else:
        return {
            "tier": "Low Match",
            "label": "Low",
            "color": "red",
            "description": "Candidate may not meet requirements",
            "icon": "🔴",
        }


async def analyze_resume_node(state: InterviewState) -> dict:
    """Parse the uploaded resume PDF and extract structured candidate data.

    Reads the resume PDF at state.resume_file_path, calls parse_resume
    which uses the LLM (with regex fallback) to extract structured fields.
    Passes JD data to compute a skill match score if JD has been parsed.

    Args:
        state: Current InterviewState. Must have resume_file_path set.
                jd data fields are used for match scoring if available.

    Returns:
        Dict of state fields to update:
        resume_raw_text, candidate_name, candidate_email, candidate_phone,
        current_role, total_experience_years, candidate_skills, experience,
        education, match_score, matched_skills, missing_skills.
    """
    if not state.resume_file_path:
        logger.error("analyze_resume_node: resume_file_path is not set in state")
        return {}

    logger.info("Parsing resume from: %s", state.resume_file_path)

    # Build minimal jd_data dict for match scoring if JD was parsed
    jd_data: dict | None = None
    if state.required_skills:
        jd_data = {
            "required_skills": state.required_skills,
            "nice_to_have_skills": state.nice_to_have_skills,
        }

    try:
        data = await parse_resume(state.resume_file_path, jd_data=jd_data)
    except Exception as e:
        logger.error("analyze_resume_node: parse_resume failed: %s", e)
        return {}

    logger.info(
        "Resume parsed — candidate: %s, match score: %s%%",
        data.get("candidate_name", "Unknown"),
        data.get("match_score", 0),
    )

    # Detect gender and how to address the candidate using name-based detection
    candidate_name = data.get("candidate_name", "")
    gender_info = detect_gender_from_name(candidate_name)
    candidate_address = get_candidate_address(candidate_name)
    title = gender_info["title"]

    logger.info(
        "Gender detection: %s (confidence: %s) — address as: %s",
        gender_info["gender"],
        gender_info["confidence"],
        candidate_address,
    )

    # Compute tier from numeric match score
    numeric_score = data.get("match_score", 0)
    tier = get_match_tier(numeric_score)

    return {
        "resume_raw_text": data.get("raw_text", ""),
        "candidate_name": candidate_name,
        "candidate_title": title,
        "candidate_address": candidate_address,
        "candidate_email": data.get("email", ""),
        "candidate_phone": data.get("phone", ""),
        "current_role": data.get("current_role", ""),
        "total_experience_years": data.get("total_experience_years", 0),
        "candidate_skills": data.get("skills", []),
        "experience": data.get("experience", []),
        "education": data.get("education", []),
        "match_score": numeric_score,
        "match_tier": tier,
        "matched_skills": data.get("matched_skills", []),
        "missing_skills": data.get("missing_skills", []),
    }
