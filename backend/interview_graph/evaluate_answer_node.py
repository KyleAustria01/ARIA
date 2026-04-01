"""
evaluate_answer_node — LangGraph node that scores the candidate's latest answer.

Reads the most recent ARIA question and candidate answer from conversation_history,
calls the LLM to produce a score (1-10), feedback, a conversational hint,
and speech/emotional analysis — all in a single LLM pass.

Evaluation is internal only — nothing is added to conversation_history.
Pure async function: takes state, returns updated state dict.
"""

import json
import logging
import re

from backend.interview_graph.state import InterviewState
from backend.llm.provider import llm_invoke

logger = logging.getLogger(__name__)


def _safe_parse_json(text: str, fallback: dict) -> dict:
    """Attempt to parse a JSON dict from LLM output.

    Tries direct parse first, then extracts the first {...} block via regex.

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


async def evaluate_answer_node(state: InterviewState) -> dict:
    """Score the candidate's latest answer using a single LLM call.

    The LLM evaluates content quality, detects speech patterns (nervousness,
    stammering, incomplete answers), identifies non-answers and clarification
    requests, and determines the appropriate follow-up strategy — all in one
    pass instead of separate hardcoded heuristics.

    Args:
        state: Current InterviewState.

    Returns:
        Dict with updated scores, nervousness counters, and flags.
    """
    last_question = ""
    last_answer = ""

    for turn in reversed(state.conversation_history):
        if not last_answer and turn.role == "applicant":
            last_answer = turn.content
        elif not last_question and turn.role == "aria":
            last_question = turn.content
        if last_question and last_answer:
            break

    if not last_question or not last_answer:
        logger.warning("evaluate_answer_node: missing question or answer — skipping")
        return {}

    # Build recent conversation context for the LLM
    recent_turns: list[str] = []
    for turn in state.conversation_history[-6:]:
        prefix = "ARIA" if turn.role == "aria" else "CANDIDATE"
        recent_turns.append(f"{prefix}: {turn.content}")
    recent_context = "\n".join(recent_turns)

    prompt = f"""\
You are an expert interview evaluator analysing a candidate's answer.

Role: {state.job_title or 'the position'}
Required skills: {', '.join(state.required_skills[:8]) if state.required_skills else 'not specified'}
Consecutive nervous answers so far: {state.consecutive_nervous_count}
Non-answer count so far: {state.non_answer_count}

Recent conversation:
{recent_context}

Latest question: {last_question}
Latest answer: {last_answer}

MULTILINGUAL AWARENESS:
The candidate may answer in any language. Evaluate CONTENT regardless of
language. NEVER penalise non-English answers. Code-switching is normal.

Analyse the answer and respond with valid JSON ONLY:
{{
  "score": 7,
  "feedback": "Brief internal note on answer quality — be specific about what was good or lacking",
  "skill_area": "The specific skill/topic being assessed (e.g. 'Laravel Eloquent ORM' not just 'PHP')",
  "answer_depth": "shallow | adequate | detailed",
  "follow_up_hint": "move_on",
  "follow_up_reason": "One sentence explaining why this hint was chosen",
  "is_incomplete": false,
  "is_nervous": false,
  "is_non_answer": false,
  "is_elaborate_request": false,
  "wants_to_end": false,
  "comfort_needed": "none",
  "word_count": 45,
  "detected_language": "en",
  "topics_mentioned": ["list", "of", "specific", "topics", "candidate", "mentioned"]
}}

FIELD DEFINITIONS:

score (1-10):
  1: empty, garbled, or not a real response
  2-3: incoherent, off-topic, or nonsensical
  3-4: extremely vague, no specifics
  5-6: some understanding but lacks depth
  7-8: solid answer with relevant detail and examples
  9-10: exceptional, detailed, well-structured
  Score CONTENT only — never penalise nervousness or filler words.

skill_area: Be SPECIFIC — use the actual technology/concept name (e.g.
  "Laravel Middleware", "MySQL Query Optimization", "React State Management")
  not vague categories like "PHP" or "General".

topics_mentioned: List the specific technologies, tools, concepts, or
  experiences the candidate mentioned in their answer. This helps track
  what has been discussed.

follow_up_hint — choose ONE:
  "dig_deeper" — interesting but needs specifics, ask follow-up
  "clarify" — vague or off-topic, redirect
  "move_on" — sufficient, go to new topic
  "elaborate" — candidate asked for clarification
  "simplify" — candidate said "I don't know"
  "wrap_up" — candidate wants to end
  "continue" — answer was cut off, ask them to finish

is_incomplete: True if answer was cut off mid-sentence or is clearly unfinished.
is_nervous: True if excessive filler words or stuttering (NOT brevity).
is_non_answer: True if "I don't know", "pass", "skip", or <3 meaningful words.
is_elaborate_request: True if candidate asks you to rephrase/clarify.
wants_to_end: True if candidate signals they want to stop.
comfort_needed: "none" | "probe" | "medium" | "high" | "redirect"

Reply with ONLY the JSON object, no explanation."""

    messages = [
        {"role": "system", "content": "You are an expert interview evaluator. Respond with valid JSON only."},
        {"role": "user", "content": prompt},
    ]

    logger.info(
        "\n========================================\n"
        "ARIA PROMPT (evaluate_answer_node)\n"
        "========================================\n"
        "Question: %s\n"
        "Answer: %s\n"
        "Consecutive nervous: %d\n\n"
        "Full prompt sent to LLM:\n%s\n"
        "========================================",
        last_question[:150],
        last_answer[:200],
        state.consecutive_nervous_count,
        prompt[:2000],
    )

    fallback = {
        "score": 5,
        "feedback": "Answer received.",
        "skill_area": "General",
        "answer_depth": "adequate",
        "follow_up_hint": "move_on",
        "follow_up_reason": "",
        "is_incomplete": False,
        "is_nervous": False,
        "is_non_answer": False,
        "is_elaborate_request": False,
        "wants_to_end": False,
        "comfort_needed": "none",
        "word_count": len(last_answer.split()),
        "detected_language": "en",
        "topics_mentioned": [],
    }

    try:
        raw = await llm_invoke(messages)
        result = _safe_parse_json(raw, fallback)
    except Exception as e:
        logger.error("evaluate_answer_node: LLM failed: %s", e)
        result = {**fallback, "feedback": "Unable to evaluate answer."}

    # Extract LLM decisions
    is_incomplete = bool(result.get("is_incomplete", False))
    is_nervous = bool(result.get("is_nervous", False))
    is_non_answer = bool(result.get("is_non_answer", False))
    is_elaborate_req = bool(result.get("is_elaborate_request", False))
    wants_to_end = bool(result.get("wants_to_end", False))
    comfort_needed = result.get("comfort_needed", "none")

    # Track nervousness across consecutive turns
    if is_nervous:
        new_consec = state.consecutive_nervous_count + 1
    else:
        new_consec = 0

    # Build emotional-intelligence state updates
    ei_updates: dict = {
        "candidate_nervous": is_nervous,
        "consecutive_nervous_count": new_consec,
        "elaborate_requested": is_elaborate_req,
        "clarification_requested": is_elaborate_req,
        "last_question_asked": last_question if is_elaborate_req else "",
        "candidate_wants_to_end": wants_to_end or state.candidate_wants_to_end,
        "last_answer_quality": {
            "word_count": result.get("word_count", len(last_answer.split())),
            "is_nervous": is_nervous,
            "comfort_needed": comfort_needed,
        },
        "last_answer_incomplete": is_incomplete,
        "detected_language": result.get("detected_language", "en"),
    }

    # Override follow_up_hint based on LLM classification
    if wants_to_end:
        result["follow_up_hint"] = "wrap_up"
        result["score"] = 0
    elif is_elaborate_req:
        result["follow_up_hint"] = "elaborate"
        result["score"] = 0
    elif is_non_answer:
        result["follow_up_hint"] = "simplify"
        result["score"] = max(1, int(result.get("score", 1)))
        ei_updates["non_answer_count"] = state.non_answer_count + 1
    elif is_incomplete:
        result["follow_up_hint"] = "continue"

    # Attach question/answer for results page reference
    score_entry = {
        "score": result.get("score", 5),
        "feedback": result.get("feedback", ""),
        "skill_area": result.get("skill_area", "General"),
        "answer_depth": result.get("answer_depth", "adequate"),
        "follow_up_hint": result.get("follow_up_hint", "move_on"),
        "follow_up_reason": result.get("follow_up_reason", ""),
        "topics_mentioned": result.get("topics_mentioned", []),
        "question": last_question,
        "answer": last_answer,
    }

    logger.info(
        "evaluate_answer_node: score=%s skill=%s depth=%s hint=%s "
        "incomplete=%s nervous=%s non_answer=%s elaborate=%s wants_end=%s",
        score_entry.get("score"),
        score_entry.get("skill_area"),
        score_entry.get("answer_depth"),
        score_entry.get("follow_up_hint"),
        is_incomplete, is_nervous, is_non_answer, is_elaborate_req, wants_to_end,
    )

    return {**ei_updates, "scores": state.scores + [score_entry]}

