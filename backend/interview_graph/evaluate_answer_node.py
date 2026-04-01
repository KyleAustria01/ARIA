"""
evaluate_answer_node — LangGraph node that scores the candidate's latest answer.

Reads the most recent ARIA question and candidate answer from conversation_history,
calls the LLM to produce a score (1-10), feedback, and a conversational hint
that tells question_node whether to dig deeper, clarify, or move on.

Also performs speech-quality analysis to detect nervousness, non-answers,
and requests for elaboration — updating emotional-intelligence state fields.

Evaluation is internal only — nothing is added to conversation_history.
Pure async function: takes state, returns updated state dict.
"""

import json
import logging
import re
import unicodedata

from backend.interview_graph.prompts import (
    ARIA_SCORING_RULES,
    analyze_answer_quality,
    detect_wrap_up_request,
)
from backend.interview_graph.state import InterviewState
from backend.llm.provider import llm_invoke

logger = logging.getLogger(__name__)

# Minimum number of alphabetic characters for an answer to be considered substantive
_MIN_ALPHA_CHARS = 15

# ── Speech-quality helpers ──────────────────────────────────────────────────

_STAMMER_PATTERNS = [
    "uh ", "um ", "er ", "ah ",
    "uhh", "umm", "like like",
    "i i ", "the the ", "and and ",
    "so so ", "you know you know",
]

_NON_ANSWER_PHRASES = [
    "i don't know",
    "i do not know",
    "no idea",
    "not sure",
    "never used",
    "i have no experience",
    "i cannot answer",
    "pass",
    "skip",
    "i haven't tried",
    "i'm not familiar",
]

_ELABORATE_PATTERNS = [
    "can you elaborate",
    "can you explain",
    "what do you mean",
    "i don't understand",
    "i dont understand",
    "could you clarify",
    "more context",
    "can you give an example",
    "what exactly",
    "which part",
    "are you asking about",
    "could you rephrase",
    "can you repeat",
    "say that again",
    "make it easier",
    "make the question easier",
    "can you give a scenario",
    "give me an example",
    "give me a scenario",
    "can you elaborate on the question",
    "can you be more specific",
    "scenario",
    "example please",
    "simpler",
    "easier question",
    "different way",
    "rephrase",
    "put it differently",
]


def _analyze_speech_quality(transcript: str) -> dict:
    """Detect nervousness, stammering, and hesitation in a transcript.

    Args:
        transcript: Raw STT transcript of the candidate's answer.

    Returns:
        Dict with nervousness metrics.
    """
    text_lower = transcript.lower()
    words = text_lower.split()
    word_count = len(words)

    stammer_count = sum(text_lower.count(p) for p in _STAMMER_PATTERNS)

    too_short = word_count < 15
    incomplete = not any(transcript.strip().endswith(p) for p in (".", "!", "?"))

    nervousness_score = 0
    if stammer_count > 2:
        nervousness_score += 2
    if too_short:
        nervousness_score += 2
    if incomplete:
        nervousness_score += 1

    return {
        "is_nervous": nervousness_score >= 3,
        "is_too_short": too_short,
        "stammer_count": stammer_count,
        "word_count": word_count,
        "nervousness_score": nervousness_score,
    }


def _detect_non_answer(transcript: str) -> bool:
    """Return True if the candidate explicitly said they can't answer."""
    text_lower = transcript.lower()
    return any(p in text_lower for p in _NON_ANSWER_PHRASES)


def _detect_elaborate_request(transcript: str) -> bool:
    """Return True if the candidate is asking ARIA for clarification."""
    text_lower = transcript.lower()
    return any(p in text_lower for p in _ELABORATE_PATTERNS)


_TRAILING_INCOMPLETE = [
    "so", "and", "but", "yeah", "like", "then", "also", "or",
    "something", "etc", "basically", "actually", "well",
    # Prepositions / articles / pronouns — sentence clearly cut mid-thought
    "is", "are", "was", "were", "the", "a", "an",
    "because", "that", "which", "with", "for", "on",
    "in", "at", "to", "of", "by", "now", "currently",
    "just", "when", "where", "how", "what", "why",
    "i", "we", "they", "it", "this", "my", "our", "their",
]

_VAGUE_ENDINGS = [
    "something like that", "and so on", "and stuff",
    "and yeah", "you know", "things like that",
]


def _is_answer_incomplete(transcript: str) -> bool:
    """Check if the candidate's answer seems cut off or incomplete.

    Detects trailing filler words, very short technical answers,
    and vague endings that suggest the candidate had more to say.

    Args:
        transcript: Raw transcribed answer.

    Returns:
        True if the answer appears incomplete.
    """
    text = transcript.strip().lower()
    words = text.split()
    if not words:
        return False

    last_word = words[-1].rstrip(".!?,")
    ends_incomplete = last_word in _TRAILING_INCOMPLETE

    too_short = len(words) < 25

    vague_ending = any(text.endswith(p) for p in _VAGUE_ENDINGS)

    # Ends on a connecting/function word = clearly cut mid-sentence
    # Vague ending = likely had more to say
    # Very short + trailing = probably cut off
    return ends_incomplete or vague_ending


def _is_non_answer(text: str) -> bool:
    """Detect empty, single-punctuation, or clearly non-substantive answers.

    Returns True if the answer has fewer than _MIN_ALPHA_CHARS alphabetic
    characters after stripping whitespace and punctuation.
    """
    stripped = text.strip()
    if not stripped:
        return True
    alpha_only = "".join(
        ch for ch in stripped
        if unicodedata.category(ch).startswith("L")  # any letter
    )
    return len(alpha_only) < _MIN_ALPHA_CHARS


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
        match = re.search(r"\{.*?\}", text, re.DOTALL)
        if match:
            return json.loads(match.group())
    except Exception:
        pass
    return fallback


async def evaluate_answer_node(state: InterviewState) -> dict:
    """Score the candidate's latest answer and update emotional-intelligence state.

    Performs speech-quality analysis, detects non-answers and clarification
    requests, then calls the LLM to score the answer content (ignoring
    delivery nervousness). Updates nervousness tracking and elaborate flags.

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

    # ── Emotional-intelligence analysis ──────────────────────────────────
    speech = _analyze_speech_quality(last_answer)
    is_elaborate_req = _detect_elaborate_request(last_answer)
    is_explicit_non_answer = _detect_non_answer(last_answer)
    wants_to_end = detect_wrap_up_request(last_answer)

    # Richer quality analysis for comfort-level routing
    answer_quality = analyze_answer_quality(last_answer)

    # Detect incomplete / cut-off answers
    answer_incomplete = _is_answer_incomplete(last_answer)

    # Track nervousness across consecutive turns
    if speech["is_nervous"] or answer_quality["is_nervous"]:
        new_nervous = True
        new_consec = state.consecutive_nervous_count + 1
    else:
        new_nervous = False
        new_consec = 0

    ei_updates: dict = {
        "candidate_nervous": new_nervous,
        "consecutive_nervous_count": new_consec,
        "elaborate_requested": is_elaborate_req,
        "clarification_requested": is_elaborate_req,
        "last_question_asked": last_question if is_elaborate_req else "",
        "speech_quality_history": state.speech_quality_history + [speech],
        "candidate_wants_to_end": wants_to_end or state.candidate_wants_to_end,
        "last_answer_quality": answer_quality,
        "last_answer_incomplete": answer_incomplete,
    }

    # ── Handle wrap-up request — flag and short-circuit ──────────────────
    if wants_to_end:
        logger.info("evaluate_answer_node: candidate wants to end interview")
        score_entry = {
            "score": 0,
            "feedback": "Candidate requested to end the interview.",
            "skill_area": "General",
            "answer_depth": "none",
            "follow_up_hint": "wrap_up",
            "follow_up_reason": "Candidate signalled they want to finish.",
            "question": last_question,
            "answer": last_answer,
        }
        return {**ei_updates, "scores": state.scores + [score_entry]}

    # ── Handle elaborate request — don't score, just flag ────────────────
    if is_elaborate_req:
        logger.info("evaluate_answer_node: candidate asked for elaboration")
        score_entry = {
            "score": 0,
            "feedback": "Candidate requested clarification — not scored.",
            "skill_area": "General",
            "answer_depth": "none",
            "follow_up_hint": "elaborate",
            "follow_up_reason": "Candidate asked ARIA to rephrase or elaborate on the question.",
            "question": last_question,
            "answer": last_answer,
        }
        return {**ei_updates, "scores": state.scores + [score_entry]}

    # ── Handle explicit non-answer ("I don't know", "pass", etc.) ────────
    if is_explicit_non_answer:
        logger.info("evaluate_answer_node: explicit non-answer detected")
        new_non_count = state.non_answer_count + 1
        score_entry = {
            "score": 1,
            "feedback": "Candidate stated they cannot answer.",
            "skill_area": "General",
            "answer_depth": "shallow",
            "follow_up_hint": "simplify",
            "follow_up_reason": "Candidate said they don't know; ask a simpler related question.",
            "question": last_question,
            "answer": last_answer,
        }
        return {
            **ei_updates,
            "non_answer_count": new_non_count,
            "scores": state.scores + [score_entry],
        }

    # ── Pre-check: catch empty / non-substantive answers ─────────────────
    if _is_non_answer(last_answer):
        logger.info("evaluate_answer_node: non-substantive answer detected, auto-scoring 1")
        score_entry = {
            "score": 1,
            "feedback": "Candidate did not provide a substantive answer.",
            "skill_area": "General",
            "answer_depth": "shallow",
            "follow_up_hint": "clarify",
            "follow_up_reason": "Answer was too brief or empty to evaluate.",
            "question": last_question,
            "answer": last_answer,
        }
        return {**ei_updates, "scores": state.scores + [score_entry]}

    # ── LLM evaluation ──────────────────────────────────────────────────
    prompt = f"""\
You are evaluating a candidate's interview answer for the role of {state.job_title or 'the position'}.

Required skills: {', '.join(state.required_skills[:8]) if state.required_skills else 'not specified'}

Question asked: {last_question}

Candidate's answer: {last_answer}

{ARIA_SCORING_RULES}

Evaluate the answer and reply with valid JSON ONLY in this exact format:
{{
  "score": 7,
  "feedback": "Brief internal note on answer quality.",
  "skill_area": "The skill/topic being assessed",
  "answer_depth": "shallow",
  "follow_up_hint": "dig_deeper",
  "follow_up_reason": "Why — e.g. candidate mentioned X but didn't explain how"
}}

CONVERSATIONAL HINTS:
- answer_depth: "shallow" (vague/one-liner) | "adequate" | "detailed"
- follow_up_hint:
  - "dig_deeper" — answer was interesting but lacked specifics worth exploring
  - "clarify" — answer was vague or off-topic, needs a gentle redirect
  - "move_on" — answer was sufficient, time for a new topic
- follow_up_reason: one sentence explaining why you chose that hint"""

    messages = [{"role": "user", "content": prompt}]

    logger.info(
        "\n========================================\n"
        "ARIA PROMPT (evaluate_answer_node)\n"
        "========================================\n"
        "Question: %s\n"
        "Answer: %s\n"
        "Nervous: %s (consec: %d)\n"
        "Elaborate req: %s | Non-answer: %s\n\n"
        "Full prompt sent to LLM:\n%s\n"
        "========================================",
        last_question[:150],
        last_answer[:200],
        new_nervous, new_consec,
        is_elaborate_req, is_explicit_non_answer,
        prompt[:2000],
    )

    fallback = {
        "score": 5,
        "feedback": "Answer received.",
        "skill_area": "General",
        "answer_depth": "adequate",
        "follow_up_hint": "move_on",
        "follow_up_reason": "",
    }

    try:
        raw = await llm_invoke(messages)
        score_entry = _safe_parse_json(raw, fallback)
    except Exception as e:
        logger.error("evaluate_answer_node: LLM failed: %s", e)
        score_entry = {**fallback, "feedback": "Unable to evaluate answer."}

    # Attach question/answer for results page reference
    score_entry["question"] = last_question
    score_entry["answer"] = last_answer

    logger.info(
        "evaluate_answer_node: score=%s skill=%s depth=%s hint=%s nervous=%s",
        score_entry.get("score"),
        score_entry.get("skill_area"),
        score_entry.get("answer_depth"),
        score_entry.get("follow_up_hint"),
        new_nervous,
    )

    return {**ei_updates, "scores": state.scores + [score_entry]}

