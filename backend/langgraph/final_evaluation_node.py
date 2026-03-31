"""
LangGraph node: final_evaluation_node for ARIA AI Interview System.
Produces a structured verdict and summary for the interview.
"""
from backend.langgraph.state import InterviewState
from langchain.llms import ChatAnthropic
from backend.config import settings
from typing import Dict, Any

async def final_evaluation_node(state: InterviewState) -> InterviewState:
    """
    Produces a structured verdict and summary using LLM and updates state.
    Args:
        state (InterviewState): Current LangGraph state with answers and scores.
    Returns:
        InterviewState: Updated state with verdict set.
    """
    if not state.answers or not state.scores:
        raise ValueError("answers and scores must be set in state.")
    llm = ChatAnthropic(model="claude-3-sonnet-20240229", api_key=settings.gemini_api_key)
    prompt = (
        f"Given the following interview answers and scores, produce a final verdict and summary as JSON.\n"
        f"Answers: {state.answers}\n"
        f"Scores: {state.scores}\n"
        "Include: overall_score (1-5), strengths, weaknesses, and a verdict (pass/fail)."
    )
    # LangChain LLM is synchronous, so run in executor
    import asyncio
    loop = asyncio.get_event_loop()
    def ask_llm(prompt: str) -> str:
        return llm(prompt)
    verdict_json = await loop.run_in_executor(None, ask_llm, prompt)
    import json
    verdict: Dict[str, Any] = json.loads(verdict_json)
    state.verdict = verdict
    state.history.append({"type": "final_verdict", "message": verdict})
    return state
