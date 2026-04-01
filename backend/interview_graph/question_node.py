"""
question_node — LangGraph node that generates ARIA's next conversational turn.

ARIA behaves like a skilled human interviewer: she acknowledges answers,
gives brief natural reactions, asks follow-ups when interesting, and
transitions smoothly between topics.  She adapts when candidates are
nervous, ask for clarification, or don't know the answer.

All conversational decisions are LLM-driven — no hardcoded response
templates. The LLM receives full context (evaluation hints, emotional
state, skill coverage) and decides what to say.

The output is a single spoken turn — NOT a bare question.
Pure async function: takes state, returns updated state dict.
"""

import logging
import time

from backend.interview_graph.prompts import (
    ARIA_PERSONALITY,
    COMFORT_SCENARIOS,
    get_covered_skills,
)
from backend.interview_graph.state import InterviewState, ConversationTurn
from backend.llm.provider import llm_invoke

logger = logging.getLogger(__name__)

# System prompt is constant — sent as a system message for better LLM adherence
_SYSTEM_PROMPT = f"""\
{ARIA_PERSONALITY}

{COMFORT_SCENARIOS}

RESPONSE RULES:
1. ALWAYS reference something SPECIFIC from their last answer — never generic praise.
2. Ask about skills from the UNCOVERED list — do NOT repeat covered topics.
3. ONE clear question only — never multiple questions in one turn.
4. Keep total response under 3 sentences.
5. If the answer seemed incomplete, ask them to continue instead of a new question.
6. Build on what was said — your response must connect to the candidate's words.
7. NEVER use the phrasing "Can you walk me through..." — vary your questions.

QUESTION VARIETY — use different question formats:
- "How did you handle X in that project?"
- "What was the trickiest part of working with X?"
- "Tell me about a time when X went wrong — how did you debug it?"
- "If you had to rebuild that system today, what would you change?"
- "What trade-offs did you consider when choosing X over Y?"
- "How do you typically approach X when starting a new project?"
- "What's your testing strategy look like for X?"
- "Walk me through your debugging process when X happens."

CRITICAL — ALWAYS RESPOND TO WHAT WAS JUST SAID:
Your response MUST connect to the candidate's last message.
- If they mentioned working on something, ask about that thing.
- If they started describing a project, ask a follow-up on that project.
- NEVER jump to a completely different topic without transitioning naturally.
- The uncovered skills list is a GUIDE, not a script.
- Real conversations follow what was said, not a predetermined checklist.

NEVER RECITE THE RESUME:
- Do NOT say "I noticed you have experience with X"
- Do NOT say "I can see from your resume that..."
- Do NOT say "Your background shows..."
- Do NOT describe the candidate's skills back to them
- Use resume knowledge to ask BETTER questions, not to quote it back
"""


async def question_node(state: InterviewState) -> dict:
    """Generate ARIA's next conversational turn using the LLM.

    Uses a system + user message pair for better LLM adherence.
    The user message contains dynamic context (conversation history,
    evaluation hints, emotional state, skill coverage).

    Args:
        state: Current InterviewState.

    Returns:
        Dict with updated 'conversation_history', 'question_count',
        'covered_skills', and 'last_aria_opener'.
    """
    is_first = state.question_count == 0

    # Build conversation history for context
    history_lines: list[str] = []
    for turn in state.conversation_history:
        prefix = "ARIA" if turn.role == "aria" else "CANDIDATE"
        history_lines.append(f"{prefix}: {turn.content}")
    history_text = "\n".join(history_lines) if history_lines else "(no conversation yet)"

    # Track covered skills
    covered_skills, uncovered = get_covered_skills(
        state.conversation_history,
        state.required_skills,
    )

    # Also consider skills from evaluation feedback
    for s in state.scores:
        area = s.get("skill_area", "")
        if area and area != "General" and area not in covered_skills:
            covered_skills.append(area)
            if area in uncovered:
                uncovered.remove(area)

    # Pull the latest evaluation context
    follow_up_hint = "move_on"
    follow_up_reason = ""
    if state.scores:
        latest = state.scores[-1]
        follow_up_hint = latest.get("follow_up_hint", "move_on")
        follow_up_reason = latest.get("follow_up_reason", "")

    # Get the last ARIA question (for rephrase/elaborate context)
    last_aria_question = ""
    for turn in reversed(state.conversation_history):
        if turn.role == "aria":
            last_aria_question = turn.content
            break

    # Get the candidate's last answer for context
    last_candidate_answer = ""
    for turn in reversed(state.conversation_history):
        if turn.role == "applicant":
            last_candidate_answer = turn.content
            break

    candidate_addr = state.candidate_address or (state.candidate_name or "the candidate").split()[0]

    if is_first:
        user_prompt = f"""\
This is the VERY FIRST technical question of the interview. You've already
greeted the candidate and they responded with their intro.

ROLE: {state.job_title or 'the position'} {('at ' + state.company) if state.company else ''}
CANDIDATE: {state.candidate_name or 'the candidate'} (address as "{candidate_addr}")
Current role: {state.current_role or 'not specified'}

KEY SKILLS TO ASSESS (prioritize the first ones):
{', '.join(state.required_skills[:8]) if state.required_skills else 'general technical competency'}

FULL CONVERSATION SO FAR:
{history_text}

CANDIDATE'S LAST MESSAGE: "{last_candidate_answer[:500]}"

INSTRUCTION:
Generate your first interview question. Rules:
- If the candidate mentioned something specific in their intro, BUILD ON IT
  (e.g. if they mentioned a project, ask about that project's technical details)
- If the intro was very brief ("thank you", "hello", etc.), ask a natural
  opener about their most recent work experience
- Ask ONE clear question — no multi-part questions
- Keep it under 2 sentences
- Make it feel like a natural start, not an interrogation
- DO NOT use "Can you walk me through..." — instead try "Tell me about...",
  "What was...", "How did you..."
- Output ONLY the spoken text — no quotes, no labels"""
    else:
        user_prompt = f"""\
INTERVIEW CONTEXT:
{state.interview_context[:2000] if state.interview_context else 'No additional context.'}

CANDIDATE: {state.candidate_name or 'the candidate'} (address as "{candidate_addr}")
Role: {state.job_title or 'the position'}
Current role: {state.current_role or 'not specified'}

SKILLS STILL TO COVER (prioritize these):
{', '.join(uncovered[:5]) if uncovered else 'Most key skills have been touched on — dig deeper on weak areas'}

SKILLS ALREADY COVERED (do NOT ask about these again):
{', '.join(covered_skills) if covered_skills else 'None yet'}

LATEST EVALUATION:
Follow-up hint: {follow_up_hint}
Reason: {follow_up_reason}
Last ARIA question: "{last_aria_question[:200]}"
Candidate's last answer: "{last_candidate_answer[:500]}"

EMOTIONAL STATE:
Candidate nervous: {state.candidate_nervous} (consecutive: {state.consecutive_nervous_count})
Answer incomplete (cut off): {state.last_answer_incomplete}
Clarification requested: {state.clarification_requested}
Candidate wants to end: {state.candidate_wants_to_end}
Detected language: {state.detected_language}

LANGUAGE RULE:
The candidate's detected language is "{state.detected_language}".
If NOT English, you MUST still respond in ENGLISH only. Understand their
content regardless of language — NEVER ask them to switch to English.

WHAT YOU MUST DO BASED ON follow_up_hint:

- "continue": Answer was cut off. Say "Please go on" or "Continue — what
  were you saying?" Do NOT ask a new question.

- "elaborate": Candidate asked you to clarify. Rephrase "{last_aria_question[:150]}"
  with a real-world scenario. Do NOT change topic. Do NOT repeat word-for-word.

- "simplify": Candidate said "I don't know". Respond with empathy and ask
  a SIMPLER version about the same topic area.

- "dig_deeper": Answer was interesting but lacked specifics. Ask a follow-up
  about what they JUST said — reference their specific words.

- "clarify": Answer was vague or off-topic. Gently redirect with a specific
  example prompt.

- "move_on": Previous topic is covered. TRANSITION NATURALLY to a new skill
  from the uncovered list. Reference something from the conversation so far
  to bridge topics.

- "wrap_up": Candidate wants to end. If question_count >= 5, wrap up
  gracefully. Otherwise, say "Just one more quick one" and ask about the
  most critical uncovered skill.

Current hint: **{follow_up_hint}**

FULL CONVERSATION:
{history_text}

This is question {state.question_count + 1} of up to {state.max_questions}.
Generate your next conversational turn. Output ONLY the spoken text — no
quotes, no labels, no markdown."""

    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    logger.info(
        "\n========================================\n"
        "ARIA PROMPT (question_node)\n"
        "========================================\n"
        "Candidate: %s\n"
        "Question #%d\n"
        "Follow-up hint: %s\n"
        "Nervous: %s (consecutive: %d)\n"
        "Incomplete: %s | Clarification: %s\n"
        "Last answer: %s\n"
        "========================================",
        state.candidate_name,
        state.question_count + 1,
        follow_up_hint,
        state.candidate_nervous,
        state.consecutive_nervous_count,
        state.last_answer_incomplete,
        state.clarification_requested,
        last_candidate_answer[:100],
    )

    try:
        response = await llm_invoke(messages)
        response = response.strip().strip('"').strip()
    except Exception as e:
        logger.error("question_node: LLM failed: %s", e)
        # Context-aware fallback that references what the candidate said
        if is_first and last_candidate_answer and len(last_candidate_answer) > 20:
            response = (
                f"Thanks for that overview. What's the most technically "
                f"challenging project you've worked on recently, and what "
                f"made it challenging?"
            )
        elif is_first:
            response = (
                f"Tell me about your most recent project — what were you "
                f"building and what was your role in it?"
            )
        elif uncovered:
            skill = uncovered[0]
            response = (
                f"That's helpful context. Switching gears a bit — "
                f"how do you typically approach {skill} in your projects?"
            )
        else:
            response = (
                f"Interesting. Tell me about a technical challenge you "
                f"faced recently and how you solved it."
            )

    # Determine if this counts as a new question or a follow-up
    is_follow_up = False
    if state.last_answer_incomplete:
        is_follow_up = True
    elif not is_first and state.clarification_requested:
        is_follow_up = True
    elif not is_first and follow_up_hint in ("dig_deeper", "clarify", "elaborate", "simplify", "continue", "wrap_up"):
        is_follow_up = True

    new_count = state.question_count if is_follow_up else state.question_count + 1

    logger.info(
        "question_node: Q%d%s — %s",
        new_count,
        " (follow-up)" if is_follow_up else "",
        response[:120],
    )

    new_turn = ConversationTurn(
        role="aria",
        content=response,
        timestamp=time.time(),
    )

    return {
        "conversation_history": state.conversation_history + [new_turn],
        "question_count": new_count,
        "covered_skills": covered_skills,
        "last_aria_opener": "",
    }
