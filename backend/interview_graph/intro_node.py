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

    prompt = f"""{ARIA_PERSONALITY}

You are starting a pre-screening interview for {state.company or 'our company'}.

Candidate: {state.candidate_name or 'the candidate'}
How to address them: "{address}"
Role: {state.job_title or 'the open position'}
{current_role_line}
{skills_line}
{exp_line}

Write a warm, conversational interview introduction that:
1. Greets the candidate as "{address}"
2. Introduces yourself as ARIA briefly (one clause, not a speech)
3. Mentions the role they're interviewing for
4. Says this will be a relaxed ~10-15 minute conversation
5. Ends by asking them to start by walking you through their background —
   their career journey, what they've been working on recently, and what
   brought them to apply for this role

Keep it to 4-5 sentences MAX. Sound natural when spoken aloud.
Do NOT list bullet points or use formal corporate language.
Do NOT ask a technical question.
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
        intro_text = await llm_invoke([{"role": "user", "content": prompt}])
    except Exception as exc:
        logger.warning("LLM intro generation failed (%s), using fallback", exc)
        intro_text = (
            f"Good day, {address}! Welcome — I'm ARIA, and I'll be chatting with you today "
            f"about the {state.job_title or 'open'} position"
            f"{' at ' + state.company if state.company else ''}. "
            "This should be a pretty relaxed conversation, about 10 to 15 minutes. "
            "To kick things off, I'd love to hear you walk me through your background — "
            "your career journey so far, what you've been working on recently, "
            "and what got you interested in this role."
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
