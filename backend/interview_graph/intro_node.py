"""
intro_node — LangGraph node that generates ARIA's opening introduction.

Produces a warm, professional greeting that:
- Addresses the candidate by name
- Introduces ARIA and the role
- Asks the candidate to walk through their resume / background
- Sets a conversational tone from the very start

No technical questions are asked in this node.
"""

import logging
import time

from backend.interview_graph.prompts import ARIA_PERSONALITY
from backend.interview_graph.state import ConversationTurn, InterviewState
from backend.llm.provider import llm_invoke

logger = logging.getLogger(__name__)


async def intro_node(state: InterviewState) -> dict:
    """Generate ARIA's spoken introduction for the interview.

    Uses the LLM to craft a natural, warm greeting that ends with
    asking the candidate to walk through their resume / background.

    Args:
        state: InterviewState with JD and resume fields populated.

    Returns:
        Dict with conversation_history and interview_started_at updates.
    """
    # Use the pre-computed formal address (Mr. Smith / Ms. Jones / FirstName)
    address = state.candidate_address or (state.candidate_name or "there").split()[0]

    # Build a brief profile snippet so ARIA can reference their background
    current_role_line = f"Their current/recent role: {state.current_role}" if state.current_role else ""
    skills_line = f"Their key skills: {', '.join(state.candidate_skills[:6])}" if state.candidate_skills else ""
    exp_line = f"Total experience: ~{state.total_experience_years} years" if state.total_experience_years else ""

    first_name = address.split()[0] if address else "there"

    prompt = f"""Write a natural, warm interview opening for {address}.

Role: {state.job_title or 'the open position'}
Company: {state.company or 'our company'}
{current_role_line}
{skills_line}
{exp_line}

The opening must:
1. Introduce yourself as ARIA briefly
2. Mention the role: {state.job_title or 'the position'}
3. Set a relaxed, conversational tone
4. End by asking them to walk you through their resume or background

Keep it to 3-4 sentences maximum.
Sound like a real person starting a conversation, not reading a script.

DO NOT say:
- "It is a pleasure to meet you"
- "Good morning" or "Good afternoon" or "Good evening"
- "I see you have a strong background"
- "We are excited to have you"
- "Welcome to this interview"
- "What have you been working on most recently"

DO say something like:
"Hi {first_name}, I am ARIA and I will be conducting your pre-screening today
for the {state.job_title or 'open'} position. Let us keep this conversational —
could you walk me through your resume and tell me a bit about yourself?"

Output ONLY the spoken text."""

    logger.info(
        "\n========================================\n"
        "ARIA PROMPT (intro_node)\n"
        "========================================\n"
        "Candidate: %s\n"
        "Address as: %s\n"
        "Role: %s\n"
        "Company: %s\n\n"
        "Full prompt sent to LLM:\n%s\n"
        "========================================",
        state.candidate_name, address, state.job_title, state.company, prompt,
    )

    try:
        intro_text = await llm_invoke([
            {"role": "system", "content": ARIA_PERSONALITY},
            {"role": "user", "content": prompt},
        ])
    except Exception as exc:
        logger.warning("LLM intro generation failed (%s), using fallback", exc)
        intro_text = (
            f"Hi {address.split()[0] if address else 'there'}, I am ARIA and I will be handling "
            f"your pre-screening today for the {state.job_title or 'open'} position"
            f"{' at ' + state.company if state.company else ''}. "
            "Let us keep this conversational — could you walk me through "
            "your resume and tell me a bit about yourself?"
        )

    greeting_turn = ConversationTurn(
        role="aria",
        content=intro_text.strip(),
        timestamp=time.time(),
    )

    return {
        "conversation_history": [greeting_turn],
        "interview_started_at": time.time(),
    }
