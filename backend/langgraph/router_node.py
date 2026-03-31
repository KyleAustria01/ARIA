"""
LangGraph node: router_node for ARIA AI Interview System.
Decides whether to ask more questions or finalize the interview.
"""
from backend.langgraph.state import InterviewState

async def router_node(state: InterviewState) -> InterviewState:
    """
    Decides whether to continue asking questions or finalize the interview.
    Args:
        state (InterviewState): Current LangGraph state with questions and answers.
    Returns:
        InterviewState: Updated state with routing decision in history.
    """
    # Example logic: ask up to 5 questions, then finalize
    max_questions = 5
    if len(state.questions) < max_questions:
        decision = "ask_more"
    else:
        decision = "finalize"
    state.history.append({"type": "router_decision", "decision": decision})
    return state
