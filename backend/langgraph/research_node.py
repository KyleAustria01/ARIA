"""
LangGraph node: research_node for ARIA AI Interview System.
Uses Tavily API to supplement JD text with relevant web research.
"""
from typing import Any
from backend.langgraph.state import InterviewState
from tavily import TavilyClient
from backend.config import settings

async def research_node(state: InterviewState) -> InterviewState:
    """
    Supplements JD text with Tavily web research and updates state.
    Args:
        state (InterviewState): Current LangGraph state with jd_text set.
    Returns:
        InterviewState: Updated state with research set.
    """
    if not state.jd_text:
        raise ValueError("No jd_text set in state.")
    client = TavilyClient(api_key=settings.tavily_api_key)
    # Tavily API is async
    query = state.jd_text[:500]  # Use first 500 chars as context
    results = await client.search(query=query, max_results=5)
    research = "\n".join([r["content"] for r in results["results"]])
    state.research = research
    return state
