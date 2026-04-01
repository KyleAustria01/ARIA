"""
router_node — LangGraph node that decides whether to continue or end the interview.

Uses the LLM to evaluate whether enough information has been gathered
to make a hiring recommendation. All routing decisions are LLM-driven
except for the hard cap at max_questions (safety net).

Pure function: takes state, returns updated state dict.
"""

import json
import logging
import re

from backend.interview_graph.state import InterviewState
from backend.llm.provider import llm_invoke

logger = logging.getLogger(__name__)


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


async def router_node(state: InterviewState) -> dict:
    """Let the LLM decide whether to continue or finalize the interview.

    The LLM receives all interview context — scores, conversation history,
    skill coverage, candidate signals — and decides whether to continue
    or end. The only hardcoded rule is the max_questions safety cap.

    Args:
        state: Current InterviewState.

    Returns:
        Dict with 'is_complete' and optionally 'wrap_up_acknowledged'.
    """
    # Hard cap — always finalize at max (safety net only)
    if state.question_count >= state.max_questions:
        logger.info(
            "router_node: finalize — reached hard cap (%d questions)",
            state.question_count,
        )
        return {"is_complete": True}

    # Build conversation summary
    qa_pairs: list[str] = []
    for turn in state.conversation_history:
        role_label = "ARIA" if turn.role == "aria" else "CANDIDATE"
        qa_pairs.append(f"{role_label}: {turn.content}")
    conversation = "\n".join(qa_pairs[-20:])

    # Compute average score
    avg_score: float = 0.0
    scored = [s for s in state.scores if s.get("score", 0) > 0]
    if scored:
        avg_score = sum(float(s.get("score", 5)) for s in scored) / len(scored)

    # Get latest evaluation hint
    latest_hint = ""
    latest_reason = ""
    if state.scores:
        latest_hint = state.scores[-1].get("follow_up_hint", "move_on")
        latest_reason = state.scores[-1].get("follow_up_reason", "")

    # Build skill coverage info
    covered = state.covered_skills or []
    uncovered = [s for s in state.required_skills if s not in covered]

    prompt = f"""\
You are the routing engine for an AI pre-screening interview. Decide whether
the interview should CONTINUE or be COMPLETED.

=== INTERVIEW STATUS ===
Candidate: {state.candidate_name or 'the candidate'}
Role: {state.job_title or 'the position'}
Company: {state.company or 'not specified'}
Questions asked: {state.question_count}
Max allowed: {state.max_questions}
Average score: {avg_score:.1f}/10 (from {len(scored)} scored answers)
Non-answer count: {state.non_answer_count}
Candidate wants to end: {state.candidate_wants_to_end}
Candidate nervous count: {state.consecutive_nervous_count}

=== LATEST EVALUATION ===
Hint: {latest_hint}
Reason: {latest_reason}

=== SKILL COVERAGE ===
Required skills: {', '.join(state.required_skills[:10]) if state.required_skills else 'not specified'}
Covered so far: {', '.join(covered) if covered else 'none'}
Still uncovered: {', '.join(uncovered[:5]) if uncovered else 'all covered'}

=== RECENT CONVERSATION ===
{conversation[-3000:]}

=== DECISION GUIDELINES ===
Consider ALL of these factors:
1. Have enough required skills been assessed to form a hiring opinion?
2. Is the candidate clearly excellent or clearly unqualified? (early exit OK)
3. Are there critical required skills that haven't been asked about yet?
4. Were recent answers too vague and need follow-up?
5. Has the candidate asked to end the interview?
   - If yes AND at least 5 questions asked: allow graceful exit
   - If yes BUT fewer than 5 questions: acknowledge but continue (1-2 more)
6. Did the evaluator flag a follow-up need (dig_deeper, clarify, elaborate, simplify)?
7. Have both technical AND communication skills been evaluated?
8. Is the answer incomplete (candidate was cut off)? If so, continue.

Reply with valid JSON ONLY:
{{
  "decision": "continue" or "complete",
  "reason": "Brief explanation of why",
  "wrap_up_acknowledged": false
}}

Set wrap_up_acknowledged to true ONLY if the candidate asked to end and you
are acknowledging their request (whether continuing or completing)."""

    logger.info(
        "\n========================================\n"
        "ARIA PROMPT (router_node)\n"
        "========================================\n"
        "Questions: %d / %d\n"
        "Avg score: %.1f\n"
        "Latest hint: %s\n"
        "Wants to end: %s\n\n"
        "Prompt:\n%s\n"
        "========================================",
        state.question_count, state.max_questions,
        avg_score, latest_hint, state.candidate_wants_to_end,
        prompt[:2000],
    )

    try:
        raw = await llm_invoke([
            {"role": "system", "content": "You are an interview routing engine. Respond with valid JSON only."},
            {"role": "user", "content": prompt},
        ])
        result = _safe_parse_json(raw, {"decision": "continue", "reason": ""})
        decision = str(result.get("decision", "continue")).lower().strip()
        is_complete = "complete" in decision
        wrap_up = bool(result.get("wrap_up_acknowledged", False))
        reason = result.get("reason", "")

        logger.info(
            "router_node: LLM decided '%s' — %s (Q%d, avg %.1f)",
            decision, reason[:100], state.question_count, avg_score,
        )
    except Exception as exc:
        logger.warning("router_node: LLM routing failed (%s), using fallback", exc)
        is_complete = state.question_count >= 10
        wrap_up = False

    updates: dict = {"is_complete": is_complete}
    if wrap_up:
        updates["wrap_up_acknowledged"] = True

    return updates

