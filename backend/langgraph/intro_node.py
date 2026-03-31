"""
LangGraph node: intro_node for ARIA AI Interview System.
Generates ARIA's spoken greeting for the applicant.
"""
from backend.langgraph.state import InterviewState

async def intro_node(state: InterviewState) -> InterviewState:
    """
    Generates ARIA's greeting message and updates state.
    Args:
        state (InterviewState): Current LangGraph state with applicant_name and role set.
    Returns:
        InterviewState: Updated state with greeting in history.
    """
    if not state.applicant_name or not state.role:
        raise ValueError("applicant_name and role must be set in state.")
    greeting = (
        f"Hello {state.applicant_name}, welcome to your interview for the {state.role} position. "
        "I am ARIA, your AI interviewer. Let's begin!"
    )
    state.history.append({"type": "greeting", "message": greeting})
    return state
