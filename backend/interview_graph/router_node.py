"""
router_node — LangGraph node that decides whether to continue or end the interview.

Uses the LLM to evaluate whether enough information has been gathered
to make a hiring recommendation. The AI considers skill coverage,
answer quality, and conversation depth before deciding.

Pure function: takes state, returns updated state dict.
"""

import logging

from backend.interview_graph.state import InterviewState
from backend.llm.provider import llm_invoke

logger = logging.getLogger(__name__)

_MIN_QUESTIONS = 5
_MAX_QUESTIONS = 12


async def router_node(state: InterviewState) -> dict:
    """Let the LLM decide whether to continue or finalize the interview.

    Decision factors (handled by LLM prompt):
    - Minimum 5 questions before allowing completion
    - Hard cap at 12 questions
    - Early completion if candidate is clearly excellent or unqualified
    - Continues if important skills haven't been covered yet
    - Continues if answers were too vague
    - Handles candidate wrap-up requests gracefully

    Args:
        state: Current InterviewState.

    Returns:
        Dict with 'is_complete' set to True if interview should end,
        and optionally 'wrap_up_acknowledged' for graceful endings.
    """
    # Hard cap — always finalize at max
    if state.question_count >= _MAX_QUESTIONS:
        logger.info(
            "router_node: finalize — reached hard cap (%d questions)",
            state.question_count,
        )
        return {"is_complete": True}

    # ── Handle candidate wrap-up request ─────────────────────────────────
    latest_hint = ""
    if state.scores:
        latest_hint = state.scores[-1].get("follow_up_hint", "move_on")

    if state.candidate_wants_to_end or latest_hint == "wrap_up":
        if state.question_count >= _MIN_QUESTIONS:
            # Enough questions asked — allow graceful exit
            logger.info(
                "router_node: finalize — candidate requested wrap-up after %d questions",
                state.question_count,
            )
            return {"is_complete": True, "wrap_up_acknowledged": True}
        else:
            # Not enough questions — acknowledge but continue with 1-2 more
            logger.info(
                "router_node: continue — candidate wants wrap-up but only %d questions asked",
                state.question_count,
            )
            return {"is_complete": False, "wrap_up_acknowledged": True}

    # Below minimum — always continue
    if state.question_count < _MIN_QUESTIONS:
        logger.info(
            "router_node: continue — below minimum (%d/%d)",
            state.question_count,
            _MIN_QUESTIONS,
        )
        return {"is_complete": False}

    # If the evaluator flagged a follow-up, elaborate, or simplify, continue
    if latest_hint in ("dig_deeper", "clarify", "elaborate", "simplify"):
        logger.info(
            "router_node: continue — evaluator wants follow-up (%s)",
            latest_hint,
        )
        return {"is_complete": False}

    # Build conversation summary for the LLM
    qa_pairs: list[str] = []
    for turn in state.conversation_history:
        role_label = turn.role.upper() if hasattr(turn, "role") else "TURN"
        content = turn.content if hasattr(turn, "content") else str(turn)
        qa_pairs.append(f"{role_label}: {content}")

    conversation = "\n".join(qa_pairs[-20:])

    avg_score: float = 0.0
    if state.scores:
        total = sum(float(s.get("score", 5)) for s in state.scores)
        avg_score = total / len(state.scores)

    prompt = f"""You are evaluating an AI pre-screening interview in progress.

Role: {state.job_title}
Company: {state.company}
Required skills: {state.required_skills}
Questions asked so far: {state.question_count}
Average score so far: {avg_score:.1f}/10

Conversation so far:
{conversation}

Decide if the interview has gathered enough information to make a hiring recommendation.

Rules:
- Complete early if the candidate is clearly excellent OR clearly unqualified
- Continue if important required skills have not been asked about yet
- Continue if recent answers were too vague and need follow-up
- Consider whether technical AND behavioral aspects have been covered

Reply with ONLY one word: continue OR complete"""

    logger.info(
        "\n========================================\n"
        "ARIA PROMPT (router_node)\n"
        "========================================\n"
        "Questions so far: %d\n"
        "Avg score: %.1f\n\n"
        "Full prompt sent to LLM:\n%s\n"
        "========================================",
        state.question_count,
        avg_score,
        prompt[:2000],
    )

    try:
        response = await llm_invoke([{"role": "user", "content": prompt}])
        decision = response.lower().strip()
        is_complete = "complete" in decision
        logger.info(
            "router_node: LLM decided '%s' — %d questions, avg score %.1f",
            decision,
            state.question_count,
            avg_score,
        )
    except Exception as exc:
        # Fallback: continue if LLM fails, unless we're near the cap
        logger.warning("router_node: LLM routing failed (%s), using fallback", exc)
        is_complete = state.question_count >= 10

    return {"is_complete": is_complete}

