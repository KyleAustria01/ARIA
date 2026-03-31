"""
final_evaluation_node — LangGraph node that produces the structured verdict.

Aggregates all scores and conversation history into a comprehensive
evaluation report. Calls the LLM once to generate the verdict narrative,
then merges it with computed score statistics.
Pure async function: takes state, returns updated state dict with 'verdict'.
"""

import json
import logging
import re
import time

from backend.interview_graph.state import InterviewState
from backend.llm.provider import llm_invoke

logger = logging.getLogger(__name__)


def _safe_parse_json(text: str, fallback: dict) -> dict:
    """Extract a JSON dict from raw LLM output.

    Args:
        text: Raw LLM response string.
        fallback: Dict to return if all parsing attempts fail.

    Returns:
        Parsed dict or fallback.
    """
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


async def final_evaluation_node(state: InterviewState) -> dict:
    """Produce the final structured verdict for the completed interview.

    Computes score statistics from state.scores, then calls the LLM to
    generate a verdict narrative with strengths, concerns, and a hire
    recommendation. Merges the LLM output with computed stats into a
    single verdict dict stored in state.verdict.

    Also records interview_ended_at timestamp.

    Args:
        state: Current InterviewState. Uses scores, conversation_history,
               candidate_name, job_title, required_skills, missing_skills.

    Returns:
        Dict with 'verdict' (structured report dict) and 'interview_ended_at'.
    """
    # --- Compute score statistics ---
    scores_list = [float(s.get("score", 5)) for s in state.scores] if state.scores else []
    avg_score = round(sum(scores_list) / len(scores_list), 1) if scores_list else 0.0
    max_score = max(scores_list) if scores_list else 0.0
    min_score = min(scores_list) if scores_list else 0.0

    # Build Q&A summary for the prompt
    qa_lines: list[str] = []
    for s in state.scores:
        qa_lines.append(
            f"Q: {s.get('question', '')[:120]}\n"
            f"A: {s.get('answer', '')[:200]}\n"
            f"Score: {s.get('score', '?')}/10 — {s.get('feedback', '')}"
        )
    qa_summary = "\n\n".join(qa_lines) if qa_lines else "No scored answers available."

    # Build logistics section for the prompt
    logistics_lines: list[str] = []
    if state.salary_expectation:
        logistics_lines.append(f"Salary expectation: {state.salary_expectation}")
    if state.availability:
        logistics_lines.append(f"Availability / start date: {state.availability}")
    if state.work_arrangement:
        logistics_lines.append(f"Work arrangement preference: {state.work_arrangement}")
    if state.schedule_preference:
        logistics_lines.append(f"Schedule preference: {state.schedule_preference}")
    if state.notice_period:
        logistics_lines.append(f"Notice period: {state.notice_period}")
    logistics_text = "\n".join(logistics_lines) if logistics_lines else "Not discussed."

    # JD logistics for comparison
    jd_logistics: list[str] = []
    if state.salary_range:
        jd_logistics.append(f"JD salary range: {state.salary_range}")
    if state.location:
        jd_logistics.append(f"JD location: {state.location}")
    if state.employment_type:
        jd_logistics.append(f"JD employment type: {state.employment_type}")
    jd_logistics_text = "\n".join(jd_logistics) if jd_logistics else "Not specified in JD."

    prompt = f"""\
You are producing a final interview evaluation report for a recruiter.

Candidate: {state.candidate_name or 'the candidate'}
Role applied: {state.job_title or 'the position'}
Required skills: {', '.join(state.required_skills[:8]) if state.required_skills else 'not specified'}
Missing skills: {', '.join(state.missing_skills[:5]) if state.missing_skills else 'none'}
Resume match score: {state.match_score}%
Average interview score: {avg_score}/10 (from {len(scores_list)} questions)

Interview Q&A Summary:
{qa_summary}

=== CANDIDATE LOGISTICS ===
{logistics_text}

=== JD REQUIREMENTS ===
{jd_logistics_text}

Based on the above, produce a final evaluation as JSON with these exact keys:
{{
  "overall_verdict": "Strong Hire" | "Hire" | "Maybe" | "No Hire",
  "overall_score": {avg_score},
  "strengths": ["list of 2-4 key strengths observed"],
  "concerns": ["list of 1-3 areas of concern"],
  "recommendation": "2-3 sentence hire recommendation paragraph",
  "skill_scores": {{
    "technical": 7,
    "communication": 8,
    "problem_solving": 6,
    "culture_fit": 7
  }},
  "logistics_fit": {{
    "salary_alignment": "within range" | "above range" | "below range" | "not discussed",
    "availability_fit": "good" | "potential_delay" | "not discussed",
    "work_arrangement_fit": "matches" | "mismatch" | "flexible" | "not discussed",
    "schedule_fit": "matches" | "mismatch" | "flexible" | "not discussed",
    "logistics_notes": "Brief note on any logistics concerns or highlights"
  }}
}}

Reply with valid JSON only."""

    logger.info(
        "\n========================================\n"
        "ARIA PROMPT (final_evaluation_node)\n"
        "========================================\n"
        "Candidate: %s\n"
        "Role: %s\n"
        "Avg score: %.1f / 10\n"
        "Questions: %d\n\n"
        "Full prompt sent to LLM:\n%s\n"
        "========================================",
        state.candidate_name,
        state.job_title,
        avg_score,
        len(scores_list),
        prompt[:3000],
    )

    messages = [{"role": "user", "content": prompt}]

    try:
        raw = await llm_invoke(messages)
        llm_verdict = _safe_parse_json(
            raw,
            {
                "overall_verdict": "Maybe",
                "recommendation": "Unable to generate detailed recommendation.",
                "strengths": [],
                "concerns": [],
                "skill_scores": {},
            },
        )
    except Exception as e:
        logger.error("final_evaluation_node: LLM failed: %s", e)
        llm_verdict = {
            "overall_verdict": "Maybe",
            "recommendation": "Evaluation could not be completed automatically.",
            "strengths": [],
            "concerns": [],
            "skill_scores": {},
        }

    # Merge computed stats with LLM narrative
    verdict: dict = {
        **llm_verdict,
        "overall_score": avg_score,
        "max_score": max_score,
        "min_score": min_score,
        "questions_asked": len(scores_list),
        "candidate_name": state.candidate_name,
        "job_title": state.job_title,
        "match_score": state.match_score,
        "matched_skills": state.matched_skills,
        "missing_skills": state.missing_skills,
        "scores": state.scores,
        # Logistics info for the recruiter
        "salary_expectation": state.salary_expectation,
        "availability": state.availability,
        "work_arrangement": state.work_arrangement,
        "schedule_preference": state.schedule_preference,
        "notice_period": state.notice_period,
    }

    logger.info(
        "final_evaluation_node: verdict=%s avg_score=%.1f",
        verdict.get("overall_verdict"),
        avg_score,
    )

    return {
        "verdict": verdict,
        "interview_ended_at": time.time(),
    }

