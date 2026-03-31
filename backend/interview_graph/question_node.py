"""
question_node — LangGraph node that generates ARIA's next conversational turn.

ARIA behaves like a skilled human interviewer: she acknowledges answers,
gives brief natural reactions, asks follow-ups when interesting, and
transitions smoothly between topics.  She adapts when candidates are
nervous, ask for clarification, or don't know the answer.

The output is a single spoken turn — NOT a bare question.
Pure async function: takes state, returns updated state dict.
"""

import json
import logging
import time

from backend.interview_graph.prompts import (
    ARIA_PERSONALITY,
    get_acknowledgment,
    get_transition,
    get_covered_skills,
)
from backend.interview_graph.state import InterviewState, ConversationTurn
from backend.llm.provider import llm_invoke

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = f"""\
{ARIA_PERSONALITY}

CRITICAL RESPONSE RULES:
1. NEVER start with "I can see", "I understand", "That is great", or similar filler
2. Use VARIED acknowledgments: "Thank you.", "Noted.", "That is helpful.", or say nothing
3. Reference something SPECIFIC from their answer, not generic praise
4. Ask about skills from the UNCOVERED list below — do NOT repeat covered topics
5. ONE clear question only — never multiple questions
6. Keep total response under 3 sentences

RESPONSE FORMAT:
1. [Optional] One SHORT acknowledgment that references what they just said
2. [If transitioning] Brief bridge to the new topic
3. ONE specific technical question targeting an UNCOVERED skill

FORBIDDEN PHRASES (never use these):
- "I can see you've..."
- "I understand that..."
- "That's really great..."
- "That's very helpful..."
- "It sounds like you have..."
- "Based on what you said..."
"""

_FIRST_QUESTION_PROMPT = f"""\
{ARIA_PERSONALITY}

This is the VERY FIRST technical question of the interview (you've already
greeted the candidate).

Rules:
- Start with a natural, easy opener — something about their background or
  experience that lets them ease into the conversation
- Ask ONE clear question
- Keep it under 2 sentences
- Make it feel like a natural start, not an interrogation
- Reference their role/skills if available
- Output ONLY the spoken text
"""


async def question_node(state: InterviewState) -> dict:
    """Generate ARIA's next conversational turn.

    For the first question, uses a warm opener prompt. For subsequent
    questions, builds the full conversation context so ARIA can react
    to the candidate's answers naturally. Uses varied acknowledgments
    and focuses on uncovered JD skills.

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
    history_text = "\n".join(history_lines) if history_lines else "(none)"

    # Track covered skills using the helper function
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

    # Get a varied acknowledgment (avoiding last used)
    ack = get_acknowledgment(state.last_aria_opener)
    transition = get_transition()

    if is_first:
        user_prompt = f"""{_FIRST_QUESTION_PROMPT}

=== ROLE ===
{state.job_title or 'the position'} {('at ' + state.company) if state.company else ''}

=== CANDIDATE ===
Name: {state.candidate_name or 'the candidate'}
Address as: "{state.candidate_address or (state.candidate_name or 'the candidate').split()[0]}"
Current role: {state.current_role or 'not specified'}
Key skills: {', '.join(state.candidate_skills[:8]) if state.candidate_skills else 'not specified'}

=== KEY SKILLS TO ASSESS ===
{', '.join(state.required_skills[:8]) if state.required_skills else 'general competency'}

Ask the first interview question now."""
    else:
        # Pull the latest evaluation's follow-up hint to guide the conversation
        follow_up_hint = "move_on"
        follow_up_reason = ""
        if state.scores:
            latest = state.scores[-1]
            follow_up_hint = latest.get("follow_up_hint", "move_on")
            follow_up_reason = latest.get("follow_up_reason", "")

        # ── Emotional-intelligence context ──────────────────────────────
        # Get the last question for elaborate/simplify reference
        last_aria_question = ""
        for turn in reversed(state.conversation_history):
            if turn.role == "aria":
                last_aria_question = turn.content
                break

        ei_context = ""

        if follow_up_hint == "elaborate":
            # Candidate asked ARIA to rephrase / elaborate
            ei_context = f"""
=== CANDIDATE NEEDS CLARIFICATION ===
The candidate asked you to clarify or elaborate on this question:
"{last_aria_question}"

You MUST rephrase the question more clearly. Add a brief real-world scenario
or example to help them understand. For example:
"Let me rephrase that. Imagine you're working on a large e-commerce platform
and the database queries are running very slowly. How would you approach
diagnosing and fixing the performance issue?"

Do NOT repeat the original question word-for-word. Make it concrete and specific.
This does NOT count as a new question.
"""

        elif follow_up_hint == "simplify":
            # Candidate said "I don't know"
            ei_context = f"""
=== CANDIDATE COULD NOT ANSWER ===
The candidate said they don't know the answer to:
"{last_aria_question}"

Respond with empathy (e.g. "That's completely fine!"). Then ask a SIMPLER
related question on the SAME topic — something more beginner-level or
experience-based rather than theoretical. This does NOT count as a new question.
"""

        elif state.consecutive_nervous_count == 1:
            ei_context = """
=== CANDIDATE SHOWED SOME HESITATION ===
The candidate seems slightly nervous.
Begin your next question with a brief warm acknowledgment like:
"That is perfectly fine, take your time." or "No worries at all, let us continue."
Then ask the next question normally.
Be patient and encouraging without drawing attention to their nervousness.
"""

        elif state.consecutive_nervous_count == 2:
            ei_context = """
=== CANDIDATE IS NERVOUS ===
The candidate is showing signs of nervousness for two consecutive answers
(stammering, very short replies, hesitation).

Before asking the next question:
1. Offer explicit reassurance
2. Remind them this is just a conversation
3. Ask a slightly easier question
Example opener:
"I can tell you might be a little nervous and that is completely normal.
Let us slow down a bit. Here is a more straightforward question..."

Keep your tone extra warm and patient.
Do NOT draw attention to specific nervous behaviors like stammering.
"""

        elif state.consecutive_nervous_count >= 3:
            ei_context = """
=== CANDIDATE IS CLEARLY STRUGGLING ===
The candidate has been nervous or struggling for three or more consecutive answers.
Take a completely different approach:
1. Acknowledge their situation warmly
2. Tell them their effort is appreciated
3. Ask a very simple open-ended question
4. Give them space to speak freely
Example:
"I appreciate your effort here. Let us try something different.
Can you just tell me about a project you worked on recently that you are
proud of? Take as much time as you need."

Make the question EASY and OPEN-ENDED. No trick questions, no deep technical dives.
"""

        hint_instruction = {
            "dig_deeper": (
                "The candidate's last answer was interesting but lacked specifics. "
                "Ask a FOLLOW-UP that digs deeper into what they just said."
            ),
            "clarify": (
                "The candidate's last answer was vague or off-topic. "
                "Gently ask them to clarify or give a concrete example."
            ),
            "move_on": (
                "The previous topic has been adequately covered. "
                "Transition to a new skill area from the uncovered list."
            ),
            "elaborate": (
                "Rephrase your last question with a real-world scenario."
            ),
            "simplify": (
                "Ask a simpler version of the same topic."
            ),
            "wrap_up": (
                "The candidate has signalled they want to end. "
                "If wrap_up_acknowledged is True, ask one final focused question. "
                "Keep it brief and acknowledge their time constraint."
            ),
        }.get(follow_up_hint, "Transition to a new topic.")

        # Handle wrap-up scenario
        wrap_up_context = ""
        if state.wrap_up_acknowledged and not state.is_complete:
            wrap_up_context = f"""
=== CANDIDATE WANTS TO WRAP UP ===
The candidate has indicated they want to end the interview.
Say: "I understand. Just one more quick question before we wrap up."
Then ask ONE focused question about the most important uncovered skill:
{uncovered[0] if uncovered else 'general experience'}

Keep it SHORT. This is the last question.
"""

        user_prompt = f"""{_SYSTEM_PROMPT}

=== INTERVIEW CONTEXT ===
{state.interview_context[:2000] if state.interview_context else 'No additional context.'}

=== CANDIDATE PROFILE ===
Name: {state.candidate_name or 'the candidate'}
Address as: "{state.candidate_address or (state.candidate_name or 'the candidate').split()[0]}"
Role: {state.job_title or 'the position'}
Current role: {state.current_role or 'not specified'}
Skills: {', '.join(state.candidate_skills[:8]) if state.candidate_skills else 'not specified'}

=== SKILLS STILL TO COVER (prioritize these) ===
{', '.join(uncovered[:5]) if uncovered else 'Most key skills have been touched on'}

=== SKILLS ALREADY COVERED (do NOT ask about these again) ===
{', '.join(covered_skills) if covered_skills else 'None yet'}

=== ACKNOWLEDGMENT TO USE ===
Start with: "{ack}" (or similar — do NOT say "I can see" or "I understand")
If transitioning, use: "{transition}"

=== CONVERSATIONAL DIRECTION ===
{hint_instruction}
{('Reason: ' + follow_up_reason) if follow_up_reason else ''}
{ei_context}
{wrap_up_context}

=== FULL CONVERSATION ===
{history_text}

=== INSTRUCTION ===
This is question {state.question_count + 1} of up to {state.max_questions}.
Generate your next conversational turn (acknowledgement + question)."""

    messages = [{"role": "user", "content": user_prompt}]

    logger.info(
        "\n========================================\n"
        "ARIA PROMPT (question_node)\n"
        "========================================\n"
        "Candidate: %s\n"
        "Question #%d\n"
        "Nervous: %s (consecutive: %d)\n"
        "Elaborate requested: %s\n\n"
        "Conversation (last 4):\n%s\n\n"
        "Full prompt sent to LLM:\n%s\n"
        "========================================",
        state.candidate_name,
        state.question_count + 1,
        state.candidate_nervous,
        state.consecutive_nervous_count,
        state.elaborate_requested,
        json.dumps(
            [{"role": t.role, "content": t.content[:120]} for t in state.conversation_history[-4:]],
            indent=2,
        ),
        user_prompt[:3000],
    )

    try:
        response = await llm_invoke(messages)
        response = response.strip().strip('"').strip()
    except Exception as e:
        logger.error("question_node: LLM failed: %s", e)
        if is_first:
            response = (
                f"I'd love to start by hearing about your background. "
                f"What drew you to {state.required_skills[0] if state.required_skills else 'this field'}, "
                f"and how has your experience shaped your approach?"
            )
        else:
            response = (
                f"That's helpful context, thank you. "
                f"Can you walk me through a specific project where you used "
                f"{uncovered[0] if uncovered else 'the core skills for this role'}?"
            )

    # Follow-ups, elaborations, simplifications, and wrap-up don't count as new questions
    is_follow_up = False
    if not is_first and state.scores:
        latest_hint = state.scores[-1].get("follow_up_hint", "move_on")
        is_follow_up = latest_hint in ("dig_deeper", "clarify", "elaborate", "simplify", "wrap_up")

    new_count = state.question_count if is_follow_up else state.question_count + 1

    logger.info(
        "question_node: Q%d%s — %s",
        new_count,
        " (follow-up)" if is_follow_up else "",
        response[:80],
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
        "last_aria_opener": ack,
    }
