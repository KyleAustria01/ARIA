"""
merge_context_node — LangGraph node that assembles the interview context.

Combines structured JD data, candidate resume data, and Tavily research
into a single rich interview_context string. This context is used by
question_node and evaluate_answer_node throughout the live interview.
Pure function: takes state, returns updated state dict.
"""

import logging

from backend.interview_graph.state import InterviewState

logger = logging.getLogger(__name__)


def merge_context_node(state: InterviewState) -> dict:
    """Merge JD, resume, and research into a unified interview context string.

    Builds a structured plain-text context block that ARIA's question and
    evaluation nodes use as their knowledge base for the interview.

    Args:
        state: Current InterviewState. Reads jd/resume/research fields.

    Returns:
        Dict with key 'interview_context' containing the merged context string.
    """
    sections: list[str] = []

    # --- Job Description section ---
    jd_lines = [f"ROLE: {state.job_title or 'Not specified'}"]
    if state.company:
        jd_lines.append(f"COMPANY: {state.company}")
    if state.location:
        jd_lines.append(f"LOCATION: {state.location}")
    if state.employment_type:
        jd_lines.append(f"EMPLOYMENT TYPE: {state.employment_type}")
    if state.experience_required:
        jd_lines.append(f"EXPERIENCE REQUIRED: {state.experience_required}")
    if state.required_skills:
        jd_lines.append(f"REQUIRED SKILLS: {', '.join(state.required_skills)}")
    if state.nice_to_have_skills:
        jd_lines.append(f"NICE TO HAVE: {', '.join(state.nice_to_have_skills)}")
    if state.responsibilities:
        jd_lines.append("RESPONSIBILITIES:")
        jd_lines.extend(f"  - {r}" for r in state.responsibilities[:8])
    if state.qualifications:
        jd_lines.append("QUALIFICATIONS:")
        jd_lines.extend(f"  - {q}" for q in state.qualifications[:5])

    sections.append("=== JOB DESCRIPTION ===\n" + "\n".join(jd_lines))

    # --- Candidate Resume section ---
    candidate_lines = [f"CANDIDATE: {state.candidate_name or 'Unknown'}"]
    if state.current_role:
        candidate_lines.append(f"CURRENT ROLE: {state.current_role}")
    if state.total_experience_years:
        candidate_lines.append(f"EXPERIENCE: {state.total_experience_years} years")
    if state.candidate_skills:
        candidate_lines.append(f"SKILLS: {', '.join(state.candidate_skills)}")
    if state.matched_skills:
        candidate_lines.append(f"MATCHED JD SKILLS: {', '.join(state.matched_skills)}")
    if state.missing_skills:
        candidate_lines.append(f"MISSING JD SKILLS: {', '.join(state.missing_skills)}")
    candidate_lines.append(f"MATCH SCORE: {state.match_score}%")

    sections.append("=== CANDIDATE PROFILE ===\n" + "\n".join(candidate_lines))

    # --- Research section (truncated to keep context manageable) ---
    if state.research_context:
        research_snippet = state.research_context[:3000]
        sections.append("=== INDUSTRY RESEARCH ===\n" + research_snippet)

    interview_context = "\n\n".join(sections)

    logger.info(
        "merge_context_node complete — context length: %d chars",
        len(interview_context),
    )

    return {"interview_context": interview_context}

