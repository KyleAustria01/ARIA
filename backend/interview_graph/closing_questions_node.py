"""
closing_questions_node — LangGraph node that asks logistics / fit questions.

After the technical/behavioral interview is complete, ARIA asks about:
- Expected salary (if JD has a salary range)
- Availability / notice period
- Work arrangement preference (remote, hybrid, on-site)
- Schedule preference (full-time, part-time, shift)

Questions are tailored to what the JD actually specifies. If the JD doesn't
mention salary or location, those questions are skipped.

This is NOT a scored node — it gathers practical information for the recruiter.
"""

import json
import logging
import re
import time

from backend.interview_graph.state import ConversationTurn, InterviewState
from backend.llm.provider import llm_invoke

logger = logging.getLogger(__name__)


def _build_logistics_questions(state: InterviewState) -> list[str]:
    """Determine which logistics questions to ask based on JD data.

    Args:
        state: InterviewState with JD fields populated.

    Returns:
        List of natural-language questions ARIA should ask.
    """
    questions: list[str] = []

    # Always ask availability / notice period
    questions.append(
        "Before we wrap up, I have a few quick practical questions. "
        "First — what does your availability look like? When would you "
        "be able to start if things move forward?"
    )

    # Salary — ask if JD mentions salary or it's generally expected
    if state.salary_range:
        questions.append(
            f"The role lists a salary range of {state.salary_range}. "
            "What are your salary expectations — does that range work for you?"
        )
    else:
        questions.append(
            "What are your salary expectations for this role?"
        )

    # Work arrangement — ask if JD mentions location/remote policy
    if state.location or state.employment_type:
        location_info = state.location or ""
        emp_info = state.employment_type or ""
        context = f"{location_info} {emp_info}".strip()
        questions.append(
            f"This position is listed as {context}. "
            "What's your preference in terms of work arrangement — "
            "are you looking for remote, hybrid, or on-site?"
        )
    else:
        questions.append(
            "What's your preferred work arrangement — remote, hybrid, or on-site?"
        )

    # Schedule
    questions.append(
        "And lastly, are you looking for a full-time position, or "
        "do you have any schedule preferences I should note?"
    )

    return questions


def _safe_parse_json(text: str, fallback: dict) -> dict:
    """Extract a JSON dict from LLM output."""
    try:
        return json.loads(text)
    except Exception:
        pass
    try:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return json.loads(match.group())
    except Exception:
        pass
    return fallback


async def extract_logistics(state: InterviewState) -> dict:
    """Parse the logistics Q&A into structured fields using the LLM.

    Called after all closing questions have been asked and answered.
    Reads state.logistics_raw and extracts structured info.

    Args:
        state: InterviewState with logistics_raw populated.

    Returns:
        Dict with salary_expectation, availability, work_arrangement,
        schedule_preference, and notice_period fields.
    """
    if not state.logistics_raw:
        return {}

    qa_text = "\n".join(
        f"Q: {pair.get('question', '')}\nA: {pair.get('answer', '')}"
        for pair in state.logistics_raw
    )

    prompt = f"""\
Extract structured logistics information from this interview closing Q&A.

{qa_text}

Reply with valid JSON only:
{{
  "salary_expectation": "what the candidate said about salary, or empty string",
  "availability": "when they can start, or empty string",
  "work_arrangement": "remote / hybrid / on-site / flexible, or empty string",
  "schedule_preference": "full-time / part-time / any specifics, or empty string",
  "notice_period": "if they mentioned a notice period, or empty string"
}}"""

    try:
        raw = await llm_invoke([{"role": "user", "content": prompt}])
        parsed = _safe_parse_json(raw, {})
    except Exception as e:
        logger.error("extract_logistics: LLM failed: %s", e)
        parsed = {}

    return {
        "salary_expectation": parsed.get("salary_expectation", ""),
        "availability": parsed.get("availability", ""),
        "work_arrangement": parsed.get("work_arrangement", ""),
        "schedule_preference": parsed.get("schedule_preference", ""),
        "notice_period": parsed.get("notice_period", ""),
    }
