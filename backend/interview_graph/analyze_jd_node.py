"""
analyze_jd_node — LangGraph node for Job Description analysis.

Receives the path to an uploaded JD PDF, parses it into structured
data using pdf_parser, and populates the JD fields in InterviewState.
Pure function: takes state, returns updated state dict.
"""

import logging

from backend.interview_graph.state import InterviewState
from backend.utils.pdf_parser import parse_jd

logger = logging.getLogger(__name__)


async def analyze_jd_node(state: InterviewState) -> dict:
    """Parse the uploaded JD PDF and extract structured job data.

    Reads the JD PDF at state.jd_file_path, calls parse_jd which
    uses the LLM (with regex fallback) to extract structured fields,
    and returns a dict of updated state fields.

    Args:
        state: Current InterviewState. Must have jd_file_path set.

    Returns:
        Dict of state fields to update:
        jd_raw_text, job_title, company, location, employment_type,
        experience_required, salary_range, required_skills,
        nice_to_have_skills, responsibilities, qualifications.
    """
    if not state.jd_file_path:
        logger.error("analyze_jd_node: jd_file_path is not set in state")
        return {}

    logger.info("Parsing JD from: %s", state.jd_file_path)

    try:
        data = await parse_jd(state.jd_file_path)
    except Exception as e:
        logger.error("analyze_jd_node: parse_jd failed: %s", e)
        return {}

    logger.info(
        "JD parsed — title: %s, required skills: %s",
        data.get("job_title", ""),
        data.get("required_skills", []),
    )

    return {
        "jd_raw_text": data.get("raw_text", ""),
        "job_title": data.get("job_title", ""),
        "company": data.get("company", ""),
        "location": data.get("location", ""),
        "employment_type": data.get("employment_type", ""),
        "experience_required": data.get("experience_required", ""),
        "salary_range": data.get("salary_range", ""),
        "required_skills": data.get("required_skills", []),
        "nice_to_have_skills": data.get("nice_to_have_skills", []),
        "responsibilities": data.get("responsibilities", []),
        "qualifications": data.get("qualifications", []),
    }
