"""
LangGraph node: merge_context_node for ARIA AI Interview System.
Combines JD text and research into a single interview context.
"""
from backend.langgraph.state import InterviewState

async def merge_context_node(state: InterviewState) -> InterviewState:
    """
    Merges JD text and research into a single context string and updates state.
    Args:
        state (InterviewState): Current LangGraph state with jd_text and research set.
    Returns:
        InterviewState: Updated state with context set.
    """
    if not state.jd_text or not state.research:
        raise ValueError("jd_text and research must be set in state.")
    merged = f"Job Description:\n{state.jd_text}\n\nSupplementary Research:\n{state.research}"
    state.context = merged
    return state
