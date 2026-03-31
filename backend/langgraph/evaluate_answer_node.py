"""
LangGraph node: evaluate_answer_node for ARIA AI Interview System.
Scores the applicant's answer using LLM and updates state with feedback.
"""
from backend.langgraph.state import InterviewState
from langchain.llms import ChatAnthropic
from backend.config import settings
from typing import Dict, Any

async def evaluate_answer_node(state: InterviewState) -> InterviewState:
    """
    Scores the latest applicant answer using LLM and updates state with feedback.
    Args:
        state (InterviewState): Current LangGraph state with questions and answers.
    Returns:
        InterviewState: Updated state with new score/feedback in scores/history.
    """
    if not state.questions or not state.answers:
        raise ValueError("questions and answers must be set in state.")
    question = state.questions[-1]
    answer = state.answers[-1]
    llm = ChatAnthropic(model="claude-3-sonnet-20240229", api_key=settings.gemini_api_key)
    prompt = (
        f"Evaluate the following answer to the interview question.\n"
        f"Question: {question}\n"
        f"Answer: {answer}\n"
        "Provide a score (1-5), brief feedback, and improvement suggestion as JSON."
    )
    # LangChain LLM is synchronous, so run in executor
    import asyncio
    loop = asyncio.get_event_loop()
    def ask_llm(prompt: str) -> str:
        return llm(prompt)
    feedback_json = await loop.run_in_executor(None, ask_llm, prompt)
    import json
    feedback: Dict[str, Any] = json.loads(feedback_json)
    state.scores.append(feedback)
    state.history.append({"type": "evaluation", "message": feedback})
    return state
